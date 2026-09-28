"""How the demo's feedback actually reaches GitHub - `gh`, and what happens when it is not there.

`_feedback.py`'s asking half is covered in `test_demo_cli.py`. This is the filing half: the
three functions that shell out, which is the only place in this package that runs another
program. None of it had been executed, so `subprocess` is patched at its call site and the
assertions are about the ARGV that would have run - the thing that decides what happens on a
real machine.
"""
from __future__ import annotations

import subprocess

import pytest

from csa_google_workspace.demo import _feedback


class Result:
    """Stands in for `subprocess.CompletedProcess` - only the three fields used here."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


@pytest.fixture
def gh(monkeypatch):
    """`gh` present at a known absolute path, with a scriptable `subprocess.run`.

    Returns the list of argvs that were run, so each test asserts on what would have been
    executed rather than on the return value alone.
    """
    calls = []
    monkeypatch.setattr(_feedback.shutil, "which",
                        lambda name: "/opt/homebrew/bin/gh" if name == "gh" else None)

    def install(*results):
        queue = list(results)

        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            return queue.pop(0) if queue else Result()

        monkeypatch.setattr(_feedback.subprocess, "run", fake_run)
        return calls

    install.calls = calls
    return install


class TestResolvingGh:
    def test_it_returns_an_absolute_path_not_a_bare_name(self, gh):
        """A bare "gh" is looked up on PATH at exec time, so a directory earlier on PATH
        decides what runs. Resolving once removes that question, and it is the reason this is
        a function rather than a string constant."""
        gh()
        assert _feedback._gh() == "/opt/homebrew/bin/gh"

    def test_a_missing_gh_is_none_not_an_exception(self, monkeypatch):
        monkeypatch.setattr(_feedback.shutil, "which", lambda name: None)
        assert _feedback._gh() is None


class TestCanFileDirectly:
    def test_present_and_authenticated(self, gh):
        calls = gh(Result(returncode=0))
        assert _feedback.can_file_directly() is True
        assert calls[0][0] == ["/opt/homebrew/bin/gh", "auth", "status"]

    def test_present_but_not_authenticated_is_false(self, gh):
        """Both conditions, deliberately. An unauthenticated `gh` fails at the END of a flow
        the person has already agreed to, which is the worst place to find out - so the check
        runs before the question rather than after the answer."""
        gh(Result(returncode=1, stderr="not logged in"))
        assert _feedback.can_file_directly() is False

    def test_absent_gh_never_runs_anything(self, monkeypatch):
        monkeypatch.setattr(_feedback.shutil, "which", lambda name: None)
        monkeypatch.setattr(_feedback.subprocess, "run",
                            lambda *a, **k: pytest.fail("ran a program that is not installed"))
        assert _feedback.can_file_directly() is False


class TestFilingTheIssue:
    def test_a_successful_file_returns_the_url(self, gh):
        gh(Result(returncode=0, stdout="https://github.com/o/r/issues/12\n"))
        filed, message = _feedback.file_issue("A title", "A body", "o/r")
        assert filed is True
        assert message == "https://github.com/o/r/issues/12"

    def test_the_persons_words_are_arguments_and_cannot_become_commands(self, gh):
        """A list argv with no shell. The body is somebody's free text typed at a prompt, so
        whatever punctuation is in it - backticks, semicolons, `$(...)` - has to arrive as
        data. `shell=True` here would make a comment executable."""
        calls = gh(Result(returncode=0, stdout="url"))
        nasty = "it broke; rm -rf ~ && echo `whoami` $(id)"
        _feedback.file_issue("T", nasty, "o/r")

        argv, kwargs = calls[0]
        assert isinstance(argv, list)
        assert kwargs.get("shell", False) is False, "never through a shell"
        assert nasty in argv, "the body is one argv element, verbatim"

    def test_the_label_is_applied_without_being_asked_for(self, gh):
        """Every issue this produces is the same kind of thing. A label somebody has to
        remember is a label that goes missing, and the count is the whole point of filing."""
        calls = gh(Result(returncode=0, stdout="url"))
        _feedback.file_issue("T", "B", "o/r")
        assert "--label" in calls[0][0]
        assert _feedback.LABEL in calls[0][0]

    def test_a_repo_without_the_label_yet_retries_without_it(self, gh):
        """The common failure on a fresh repo or a fork. Losing somebody's feedback to a
        missing label would be the tool discarding the thing it just asked for."""
        calls = gh(Result(returncode=1, stderr="could not add label: 'demo-feedback' not found"),
                   Result(returncode=0, stdout="https://github.com/o/r/issues/13"))
        filed, message = _feedback.file_issue("T", "B", "o/r")

        assert filed is True
        assert "https://github.com/o/r/issues/13" in message
        assert _feedback.LABEL in message, "and it says why the label is not on the issue"
        assert "--label" not in calls[1][0], "the retry is the same call minus the label"

    def test_a_retry_that_also_fails_reports_the_original_error(self, gh):
        """The FIRST error, not the second: the retry dropped the label, so its message would
        describe a call the person never asked for."""
        gh(Result(returncode=1, stderr="label 'x' not found"),
           Result(returncode=1, stderr="HTTP 403"))
        filed, message = _feedback.file_issue("T", "B", "o/r")
        assert filed is False
        assert message == "label 'x' not found"

    def test_a_non_label_failure_is_not_retried(self, gh):
        """A 403 twice is two failures, not one answer. Retrying a call that failed for a
        reason the retry does not change just delays the same message."""
        calls = gh(Result(returncode=1, stderr="HTTP 403: Resource not accessible"))
        filed, message = _feedback.file_issue("T", "B", "o/r")

        assert filed is False and "403" in message
        assert len(calls) == 1

    def test_a_failure_with_no_stderr_still_says_something(self, gh):
        """An empty message is worse than a generic one: it renders as "Could not file it: "
        with nothing after the colon."""
        gh(Result(returncode=1, stderr=""))
        filed, message = _feedback.file_issue("T", "B", "o/r")
        assert filed is False
        assert message == "gh could not create the issue"

    def test_filing_without_gh_is_reported_rather_than_attempted(self, monkeypatch):
        monkeypatch.setattr(_feedback.shutil, "which", lambda name: None)
        monkeypatch.setattr(_feedback.subprocess, "run",
                            lambda *a, **k: pytest.fail("ran a program that is not installed"))
        assert _feedback.file_issue("T", "B", "o/r") == (False, "gh is not installed")


def test_subprocess_is_the_real_one_in_this_module():
    """The fixture patches `_feedback.subprocess.run`, which is the stdlib module object - so
    a test that forgot to patch would run `gh` for real against a real repository. This pins
    the name being patched to the thing actually imported, so that mistake shows up here
    rather than as an issue filed by a test run."""
    assert _feedback.subprocess is subprocess

"""`csa-google-workspace-mcp demo` - the argument handling, the ending, and the question.

The demonstration itself is covered elsewhere (`test_demo.py`) and the unattended-sharing rule
in `test_demo_share_is_explicit.py`. What had never run is everything the *person* touches:
the per-step prompt, what is printed once the run ends, and the feedback flow - which is the
only code in this package that can post something to the internet.

`Runner` is replaced by a probe returning a synthetic `Report`, so a "run" is a few objects
rather than real Drive files. `main` still builds the real server and renders the real coverage
report from it, because that rendering is part of what the ending has to get right.
"""
from __future__ import annotations

import pytest

from csa_google_workspace.demo import _cli
from csa_google_workspace.demo._plan import Outcome, Report, Step


def outcome(status, tool="list_recent_files"):
    step = Step(tool=tool, narrate=f"{status} step", args=lambda state: {})
    return Outcome(step, status, "", None)


@pytest.fixture
def run(monkeypatch):
    """Drive `_cli.main` with a scripted Report instead of a real Drive run.

    Returns a callable taking the argv and the report to hand back, so each test says what
    the run DID and asserts what the ending said about it.
    """
    def go(argv=(), env=None, report=None, on_run=None):
        made = report if report is not None else Report()

        class Probe:
            def __init__(self, *args, **kwargs):
                self.kwargs = kwargs

            def run(self, **kwargs):
                if on_run is not None:
                    on_run(**kwargs)
                return made

        monkeypatch.setattr(_cli, "Runner", Probe)
        return _cli.main(list(argv), dict(env or {}))
    return go


class TestArguments:
    def test_help_prints_usage_and_exits_clean(self, capsys):
        assert _cli.main(["--help"], {}) == 0
        out, err = capsys.readouterr()
        assert out == "", "stdout is the JSON-RPC channel, and demo shares a process image"
        assert "usage: csa-google-workspace-mcp demo" in err

    def test_share_without_an_address_is_an_error_not_an_empty_recipient(self, capsys):
        """`--share` as the last argument. Falling through with an empty address would
        SILENTLY SKIP the sharing step - the run would look fine and never exercise the one
        operation the flag was passed to exercise."""
        assert _cli.main(["--share"], {}) == 2
        assert "--share needs an email address" in capsys.readouterr().err

    def test_the_address_after_share_is_the_one_used(self, run):
        # `--no-feedback` only so the run ends without a prompt; the flag under test is --share.
        handed = {}
        run(["--share", "someone@example.org", "--no-feedback"],
            on_run=lambda **kw: handed.update(kw))
        assert handed["share_with"] == "someone@example.org"


class TestTheStepPrompt:
    """`_ask` - what an interactive run shows before each step, and what it does with the
    answer. `--auto` replaces it with `confirm=None`, so this is the attended path only."""

    @pytest.fixture
    def step(self):
        return Step(tool="create_file", narrate="create a document",
                    args=lambda state: {},
                    teaches="Drive creates it empty. Content is a separate API.")

    @pytest.mark.parametrize("answer, expected", [
        ("", True), ("y", True), ("Y", True), ("yes", True),
        ("n", False), ("no", False), ("anything else", False),
    ])
    def test_the_default_is_yes_and_anything_unrecognised_is_no(
            self, step, monkeypatch, capsys, answer, expected):
        """Enter means go, because that is what the instructions say. Anything the prompt did
        not offer means SKIP rather than go: this creates and shares real files, so an
        unrecognised answer must not be read as consent."""
        monkeypatch.setattr("builtins.input", lambda prompt: answer)
        assert _cli._ask(step) is expected

    @pytest.mark.parametrize("answer", ["q", "quit"])
    def test_quitting_raises_rather_than_returning_false(self, step, monkeypatch, answer):
        """`main` catches KeyboardInterrupt to say what was left behind. Returning False would
        make `q` mean "skip this one step" and carry on through the whole plan."""
        monkeypatch.setattr("builtins.input", lambda prompt: answer)
        with pytest.raises(KeyboardInterrupt):
            _cli._ask(step)

    def test_what_a_step_teaches_is_shown_before_it_is_asked(self, step, monkeypatch, capsys):
        """Sentence per line, trailing period restored. The order is the point: the
        explanation has to arrive BEFORE the prompt, or it is a caption on a decision already
        made."""
        monkeypatch.setattr("builtins.input", lambda prompt: "")
        _cli._ask(step)
        err = capsys.readouterr().err
        assert "        Drive creates it empty." in err
        assert "        Content is a separate API." in err

    def test_a_trailing_separator_does_not_print_a_blank_line(self, monkeypatch, capsys):
        """`"One thing. "` splits into a sentence and an empty string. The guard against
        printing that empty string is what keeps a stray trailing space in a plan's prose from
        showing up as a blank indented line in front of the prompt."""
        trailing = Step(tool="t", narrate="do it", args=lambda state: {},
                        teaches="Drive creates it empty. ")
        monkeypatch.setattr("builtins.input", lambda prompt: "")
        _cli._ask(trailing)
        printed = [ln for ln in capsys.readouterr().err.split("\n") if ln.startswith("    ")]
        assert printed == ["        Drive creates it empty."]

    def test_a_step_that_teaches_nothing_prints_nothing_extra(self, monkeypatch, capsys):
        bare = Step(tool="t", narrate="do it", args=lambda state: {})
        monkeypatch.setattr("builtins.input", lambda prompt: "")
        _cli._ask(bare)
        assert capsys.readouterr().err == ""


class TestTheEnding:
    def test_a_run_with_no_failures_exits_zero(self, run):
        assert run(["--auto"], report=Report(outcomes=[outcome("ok")])) == 0

    def test_a_failed_step_exits_non_zero(self, run):
        """The demonstration IS this project's end-to-end test, so the exit code is what a CI
        job reads. A run that printed FAIL and exited 0 would be a green build over a broken
        server."""
        assert run(["--auto"], report=Report(outcomes=[outcome("ok"), outcome("failed")])) == 1

    def test_a_skipped_step_is_not_a_failure(self, run):
        """Optional steps skip - sharing with no recipient, most often. Treating that as a
        failure would make the ordinary unattended run red forever."""
        assert run(["--auto"], report=Report(outcomes=[outcome("skipped")])) == 0

    def test_the_folder_link_is_printed_when_there_is_one(self, run, capsys):
        report = Report(outcomes=[outcome("ok")],
                        state={"folder_url": "https://drive.google.com/drive/folders/XYZ"})
        run(["--auto"], report=report)
        assert "The folder: https://drive.google.com/drive/folders/XYZ" in capsys.readouterr().err

    def test_keep_says_the_files_are_still_there(self, run, capsys):
        """`--keep` leaves real files in a real Drive. Saying so is the difference between a
        deliberate choice and a demo that quietly litters."""
        run(["--auto", "--keep"], report=Report(outcomes=[outcome("ok")]))
        assert "Left in place, as asked" in capsys.readouterr().err

    def test_without_keep_nothing_claims_the_files_survived(self, run, capsys):
        run(["--auto"], report=Report(outcomes=[outcome("ok")]))
        assert "Left in place" not in capsys.readouterr().err

    def test_quitting_mid_run_says_where_the_files_are_and_exits_one(self, run, capsys):
        """`q` at a prompt. The folder was already created, so the one thing the message must
        carry is that something IS out there to clean up."""
        def quit_now(**kwargs):
            raise KeyboardInterrupt

        assert run([], on_run=quit_now) == 1
        assert "Anything already created is in the folder above" in capsys.readouterr().err

    def test_auto_never_asks_for_feedback(self, run, monkeypatch):
        """Nobody is there. A prompt would hang a run somebody started before going for
        coffee - and `--auto` is the mode a scheduled job uses."""
        monkeypatch.setattr(_cli, "_feedback",
                            lambda *a: pytest.fail("an unattended run asked a question"))
        run(["--auto"], report=Report(outcomes=[outcome("ok")]))

    def test_no_feedback_suppresses_it_for_an_attended_run_too(self, run, monkeypatch):
        monkeypatch.setattr(_cli, "_feedback",
                            lambda *a: pytest.fail("--no-feedback still asked"))
        run(["--no-feedback"], report=Report(outcomes=[outcome("ok")]))

    def test_an_attended_run_is_asked(self, run, monkeypatch):
        asked = {}
        monkeypatch.setattr(_cli, "_feedback",
                            lambda report, failed, repo: asked.update(failed=failed, repo=repo))
        run([], report=Report(outcomes=[outcome("ok"), outcome("failed")]))
        assert asked == {"failed": 1, "repo": _cli.REPO}

    def test_the_repo_can_be_pointed_elsewhere(self, run, monkeypatch):
        """So somebody trying this out does not file into the real tracker by accident."""
        asked = {}
        monkeypatch.setattr(_cli, "_feedback",
                            lambda report, failed, repo: asked.update(repo=repo))
        run([], env={"CSA_GW_DEMO_REPO": "someone/fork"},
            report=Report(outcomes=[outcome("ok")]))
        assert asked["repo"] == "someone/fork"


class TestTheFeedbackQuestion:
    """The only code here that can post something to the internet.

    Every test patches `can_file_directly` and `file_issue` at their definition site, which is
    where `_feedback` imports them from. An unpatched run would shell out to `gh issue create`
    against the real repository.
    """

    @pytest.fixture(autouse=True)
    def never_really_files(self, monkeypatch):
        monkeypatch.setattr("csa_google_workspace.demo._feedback.can_file_directly",
                            lambda: pytest.fail("a test reached the real gh auth check"))
        monkeypatch.setattr("csa_google_workspace.demo._feedback.file_issue",
                            lambda *a: pytest.fail("a test reached the real gh issue create"))

    @staticmethod
    def answers(monkeypatch, *responses):
        """Scripted `input`, one response per prompt, in order."""
        queue = list(responses)
        monkeypatch.setattr("builtins.input",
                            lambda prompt: queue.pop(0) if queue else "")
        return queue

    def test_an_empty_answer_files_nothing(self, monkeypatch, capsys):
        self.answers(monkeypatch, "")
        _cli._feedback("coverage", 0, "owner/repo")
        assert "Skipped - nothing was filed." in capsys.readouterr().err

    @pytest.mark.parametrize("interrupt", [EOFError, KeyboardInterrupt])
    def test_a_closed_stdin_at_the_question_is_not_an_error(self, monkeypatch, interrupt):
        """`demo | tee log` and Ctrl-D both land here. The run already succeeded; the question
        is an extra, and an extra must not turn a good run into a traceback."""
        def raise_it(prompt):
            raise interrupt

        monkeypatch.setattr("builtins.input", raise_it)
        _cli._feedback("coverage", 0, "owner/repo")        # must not raise

    def test_the_exact_text_is_shown_before_the_post_prompt(self, monkeypatch, capsys):
        """Show, then confirm - never the other way round. This posts a person's own words
        under their name, so "this is exactly what would be posted" has to be true and has to
        arrive first."""
        self.answers(monkeypatch, "the sheet step was confusing", "n")
        _cli._feedback("COVERAGE-REPORT-MARKER", 0, "owner/repo")
        err = capsys.readouterr().err
        shown, decision = err.split("Post it?", 1) if "Post it?" in err else (err, "")
        assert "the sheet step was confusing" in shown
        assert "COVERAGE-REPORT-MARKER" in shown, "the report travels with the comment"
        assert "Not posted." in err

    @pytest.mark.parametrize("answer", ["n", "", "no", "maybe"])
    def test_anything_but_yes_declines(self, monkeypatch, capsys, answer):
        """Default no. The opposite default would post on a stray Enter."""
        self.answers(monkeypatch, "a comment", answer)
        _cli._feedback("coverage", 0, "owner/repo")
        assert "Not posted." in capsys.readouterr().err

    @pytest.mark.parametrize("interrupt", [EOFError, KeyboardInterrupt])
    def test_an_interrupt_at_the_post_prompt_declines(self, monkeypatch, interrupt):
        answered = {"n": 0}

        def scripted(prompt):
            if answered["n"] == 0:
                answered["n"] += 1
                return "a comment"
            raise interrupt

        monkeypatch.setattr("builtins.input", scripted)
        _cli._feedback("coverage", 0, "owner/repo")        # must not raise, must not post

    def test_a_yes_files_it_and_says_where(self, monkeypatch, capsys):
        filed = {}
        monkeypatch.setattr("csa_google_workspace.demo._feedback.can_file_directly", lambda: True)
        monkeypatch.setattr("csa_google_workspace.demo._feedback.file_issue",
                            lambda t, b, r: filed.update(title=t, body=b, repo=r)
                            or (True, "https://github.com/owner/repo/issues/9"))

        self.answers(monkeypatch, "it was good", "y")
        _cli._feedback("coverage", 2, "owner/repo")

        assert filed["repo"] == "owner/repo"
        assert "it was good" in filed["body"]
        assert "https://github.com/owner/repo/issues/9" in capsys.readouterr().err

    def test_without_gh_it_hands_over_a_prefilled_url(self, monkeypatch, capsys):
        """No `gh`, or an unauthenticated one. The feedback must not be lost - the person gets
        a link with their own words already in it."""
        monkeypatch.setattr("csa_google_workspace.demo._feedback.can_file_directly", lambda: False)
        self.answers(monkeypatch, "here is my comment", "y")
        _cli._feedback("coverage", 0, "owner/repo")

        err = capsys.readouterr().err
        assert "Open this to post it yourself" in err
        assert "/issues/new?" in err and "here+is+my+comment" in err

    def test_a_failed_gh_call_still_offers_the_url(self, monkeypatch, capsys):
        """The worst moment to lose it: they agreed, and the tool tried and failed."""
        monkeypatch.setattr("csa_google_workspace.demo._feedback.can_file_directly", lambda: True)
        monkeypatch.setattr("csa_google_workspace.demo._feedback.file_issue",
                            lambda t, b, r: (False, "gh: could not resolve to a Repository"))

        self.answers(monkeypatch, "my comment", "y")
        _cli._feedback("coverage", 0, "owner/repo")

        err = capsys.readouterr().err
        assert "Could not file it: gh: could not resolve to a Repository" in err
        assert "/issues/new?" in err

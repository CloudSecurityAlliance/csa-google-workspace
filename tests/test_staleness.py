"""Does this copy know it is out of date? (`_environment.latest_on_pypi` and friends.)

`report_a_problem` reported the installed version and never asked whether it was current, so a
careful report could be written in detail against something fixed three releases ago.

**No test here touches the real network.**
"""
import json
import urllib.error

import pytest

from csa_google_workspace import _environment as env


class _FakeResponse:
    def __init__(self, body):
        self._body = json.dumps(body).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestLatestOnPyPI:
    def test_it_reads_the_version(self, monkeypatch):
        monkeypatch.setattr(env.urllib.request, "urlopen",
                            lambda *a, **kw: _FakeResponse({"info": {"version": "9.9.9"}}))
        assert env.latest_on_pypi() == "9.9.9"

    @pytest.mark.parametrize("boom", [urllib.error.URLError("offline"),
                                      OSError("reset"), ValueError("not json")])
    def test_a_failure_is_none_not_an_exception(self, boom, monkeypatch):
        def raise_it(*a, **kw):
            raise boom
        monkeypatch.setattr(env.urllib.request, "urlopen", raise_it)
        assert env.latest_on_pypi() is None

    @pytest.mark.parametrize("body", [{}, {"info": {}}, {"info": {"version": ""}},
                                      {"info": {"version": 3}}])
    def test_an_unexpected_shape_is_none(self, body, monkeypatch):
        """The index's JSON is somebody else's contract; a shape change must degrade."""
        monkeypatch.setattr(env.urllib.request, "urlopen", lambda *a, **kw: _FakeResponse(body))
        assert env.latest_on_pypi() is None


class TestVersionComparison:
    def test_it_reads_a_plain_version(self):
        assert env._as_tuple("0.54.0") == (0, 54, 0)

    @pytest.mark.parametrize("value", ["1.0.0rc1", "nope", "", None, "1.0.0+local"])
    def test_anything_else_is_unknown_rather_than_a_guess(self, value):
        """A pre-release must not report as "you are behind" when it may be the opposite."""
        assert env._as_tuple(value) is None


class TestUpgradeCommand:
    @pytest.mark.parametrize("route,fragment", [
        ("pipx", "pipx upgrade"), ("uv tool", "uv tool upgrade"),
        ("pip (venv)", "pip install --upgrade"),
    ])
    def test_each_route_gets_its_own(self, route, fragment):
        assert fragment in env._upgrade_command(route)

    def test_a_working_tree_is_told_to_pull(self):
        """Telling somebody to install over their own checkout is wrong advice and possibly
        destructive to whatever is uncommitted in it."""
        assert "git pull" in env._upgrade_command("editable checkout or source tree")


class TestDescribeEnvironment:
    def test_it_makes_no_network_call_unless_asked(self, monkeypatch):
        """A stdio server must not reach the network because it booted, so every caller except
        `report_a_problem` gets the offline answer."""
        def boom(*a, **kw):
            raise AssertionError("describe_environment() reached the network by default")
        monkeypatch.setattr(env.urllib.request, "urlopen", boom)
        got = env.describe_environment()
        assert got.latest_version is None and got.is_outdated is None

    def test_behind_is_reported_with_the_command_to_fix_it(self, monkeypatch):
        monkeypatch.setattr(env, "latest_on_pypi", lambda: "999.0.0")
        got = env.describe_environment(check_pypi=True)
        assert got.is_outdated is True
        assert "OUT OF DATE" in got.as_markdown()
        assert any(got.upgrade_command in n for n in got.notes)

    def test_current_says_latest(self, monkeypatch):
        monkeypatch.setattr(env, "latest_on_pypi", lambda: env.__version__)
        got = env.describe_environment(check_pypi=True)
        assert got.is_outdated is False
        assert "(latest)" in got.as_markdown()

    def test_an_unreachable_index_is_unknown_and_says_so(self, monkeypatch):
        """`is_outdated` stays None rather than False - False would read as "you are current",
        a claim this could not make."""
        monkeypatch.setattr(env, "latest_on_pypi", lambda: None)
        got = env.describe_environment(check_pypi=True)
        assert got.is_outdated is None
        assert any("Could not reach PyPI" in n for n in got.notes)

    def test_an_offline_call_does_not_imply_it_tried(self, monkeypatch):
        """The commoner caller never asked, so the version line must carry no verdict and the
        notes must not claim a failed check."""
        got = env.describe_environment()
        assert "(latest)" not in got.as_markdown()
        assert "OUT OF DATE" not in got.as_markdown()
        assert not any("Could not reach PyPI" in n for n in got.notes)

    @pytest.mark.parametrize("published", ["1.0.0rc1", "2.0.0.post1", "0.55.0+local.1", "latest"])
    def test_a_version_this_cannot_read_produces_no_verdict_and_no_apology(
            self, published, monkeypatch):
        """PyPI answered, and what it said is not plainly numeric. `_as_tuple` is deliberately
        not a PEP 440 parser - the only question is whether the index is ahead, and guessing
        at a pre-release could report "you are behind" when it is the opposite.

        So `is_outdated` stays None, and - the part that is easy to get wrong - neither note
        fires. "Could not reach PyPI" would be false, because it was reached. Silence is the
        honest answer to a question that was asked and came back unreadable.
        """
        monkeypatch.setattr(env, "latest_on_pypi", lambda: published)
        got = env.describe_environment(check_pypi=True)

        assert got.is_outdated is None
        assert not any("Could not reach PyPI" in n for n in got.notes)
        assert not any("Upgrade and retry" in n for n in got.notes)
        assert "OUT OF DATE" not in got.as_markdown() and "(latest)" not in got.as_markdown()

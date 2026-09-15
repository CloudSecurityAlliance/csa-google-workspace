"""`report_a_problem` must be complete enough to act on and safe to publish.

Most of these are absence tests. The report exists to be pasted into a *public* tracker, so what
it must never contain matters more than what it contains, and absence is exactly what a reviewer
stops noticing after the third read.
"""
from __future__ import annotations

import asyncio
import dataclasses
import platform

import pytest

from csa_google_workspace import Workspace, __version__
from csa_google_workspace._environment import Environment, describe_environment
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server

# A real-looking id: the allowlist rejects obvious placeholders like AAA, so a test that wants a
# populated scope has to supply something that survives validation.
DOC_ID = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"
DOC_URL = f"https://docs.google.com/document/d/{DOC_ID}/edit"


def call(env: dict[str, str] | None = None) -> dict:
    settings = settings_from_env(env if env is not None else {
        "CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": DOC_URL})
    server = create_server(lambda: Workspace(FakeBackend()), settings=settings)
    return asyncio.run(server.call_tool("report_a_problem", {})).structured_content


def test_report_names_the_version_python_and_os():
    out = call()
    assert out["server_version"] == __version__
    assert out["python_version"] == platform.python_version()
    assert out["os"]
    for expected in (__version__, platform.python_version(), out["os"]):
        assert expected in out["report"]


def test_report_carries_no_file_ids():
    """The one that matters. A Drive id in a public issue is a working link to the document."""
    out = call()
    for key, value in out.items():
        assert DOC_ID not in str(value), f"{key} leaks the allowlisted file id"


def test_report_carries_no_filesystem_paths():
    """A home directory is a username, which is more than a bug report needs."""
    out = call()
    for key, value in out.items():
        if key in ("issues_url", "new_issue_url", "checklist"):
            continue                       # URLs, and a checklist that cites a URL
        text = str(value)
        assert "/Users/" not in text and "C:\\Users" not in text, f"{key} leaks a path"


def test_scopes_are_described_by_shape_not_content():
    out = call()
    assert out["read_scope"] == "every file the credentials can reach"
    assert out["modify_scope"] == "1 file"


def test_an_unrestricted_scope_says_so_rather_than_looking_configured():
    """**Inverted by the v0.31.0 defaults.** This asserted an unset modify list reported
    "nothing"; unset now means every file.

    The property is the same one from the other side: a problem report has to make the scope
    legible, because a reader diagnosing a refusal needs to know whether the allowlist was
    involved. "Everything" is the answer that must not be silently implied by an empty-looking
    field — somebody reading this report is deciding where to look next."""
    out = call({})                                   # nothing set -> unrestricted
    assert "every" in out["modify_scope"].lower() or "all" in out["modify_scope"].lower()


def test_the_issue_url_is_prefilled_with_the_report():
    out = call()
    assert out["issues_url"].endswith("/issues")
    assert out["new_issue_url"].startswith(out["issues_url"] + "/new?")
    assert "title=" in out["new_issue_url"] and "body=" in out["new_issue_url"]


def test_the_checklist_is_present_and_mentions_the_version_check():
    out = call()
    assert out["checklist"]
    assert any("pypi.org" in item for item in out["checklist"])


def test_the_tool_is_absent_without_settings():
    """A library embedder wiring its own Workspace gets the document tools and none of this -
    the same rule config and auth follow, for the same reason: it needs Settings."""
    server = create_server(lambda: Workspace(FakeBackend()))
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert "report_a_problem" not in names


class TestEnvironment:
    def test_os_is_named_the_way_a_person_would_name_it(self):
        """Not the kernel version. `platform.release()` gives "25.6.0" on macOS, which nobody
        recognises as the OS they are running, and "10" on Windows 11."""
        described = describe_environment().os
        system = platform.system()
        if system == "Darwin":
            assert described.startswith("macOS")
            assert "Darwin" not in described or not platform.mac_ver()[0]
        elif system == "Windows":
            assert described.startswith("Windows")
        assert described.strip()

    def test_markdown_is_aligned_and_lists_every_field(self):
        text = describe_environment().as_markdown()
        for label in ("csa-google-workspace", "Python", "OS", "Architecture", "mcp SDK",
                      "Installed via"):
            assert label in text

    def test_as_dict_round_trips_the_dataclass(self):
        env = describe_environment()
        assert env.as_dict()["server_version"] == env.server_version
        assert isinstance(env.as_dict()["notes"], list)

    def test_a_shared_environment_is_called_out(self, monkeypatch):
        """The note has to be able to fire and has to change what the reader does. A shared
        environment is where another project's pin holds this package at an old version, so
        "upgrade first" becomes the right first reply to the report."""
        from csa_google_workspace import _environment
        monkeypatch.setattr(_environment, "_installed_via",
                            lambda: "pip (shared environment)")
        note = " ".join(_environment.describe_environment().notes)
        assert "uv tool install" in note, "CSA standardised on uv (DEC-012); lead with it"
        assert "pipx" in note, "pipx installs still exist and the advice must work for them"

    def test_a_uv_tool_install_gets_no_note(self, monkeypatch):
        """A uv tool venv is isolated exactly as a pipx one is, so the shared-environment note
        must not fire for it. Before #447 it was reported as `pip (venv)`, which is not false but
        sends a triager looking for a cross-project pin that cannot exist there."""
        from csa_google_workspace import _environment
        monkeypatch.setattr(_environment, "_installed_via", lambda: "uv tool")
        assert _environment.describe_environment().notes == []

    def test_an_isolated_install_gets_no_note(self):
        from csa_google_workspace import _environment
        env = _environment.Environment(
            server_version="1", python_version="3.12.0", python_implementation="CPython",
            os="macOS 26", architecture="arm64", mcp_sdk_version="2.1.0", installed_via="pipx")
        assert env.notes == []

    @pytest.mark.parametrize("location,expected", [
        ("/Users/x/.local/pipx/venvs/csa-google-workspace/lib/python3.12/site-packages/"
         "csa_google_workspace", "pipx"),
        # uv tool layouts, MEASURED rather than recalled (2026-09-15): the POSIX and Windows
        # trees differ in case and in whether a pythonX.Y level exists, so `uv/tools` adjacency
        # is the only part common to both.
        ("/Users/x/.local/share/uv/tools/csa-google-workspace/lib/python3.12/site-packages/"
         "csa_google_workspace", "uv tool"),
        ("C:/Users/x/AppData/Roaming/uv/tools/csa-google-workspace/Lib/site-packages/"
         "csa_google_workspace", "uv tool"),
        ("/opt/homebrew/lib/python3.12/site-packages/csa_google_workspace", "pip"),
        ("/Users/x/GitHub/csa-google-workspace/src/csa_google_workspace", "editable"),
    ])
    def test_install_route_is_inferred_from_where_the_package_lives(self, monkeypatch,
                                                                    location, expected):
        """Worth reporting because the routes fail differently: a pipx venv upgrades cleanly, a
        shared environment can have another project's pin holding the version down, and a
        checkout may match no release at all."""
        from csa_google_workspace import _environment
        monkeypatch.setattr(_environment, "__file__", f"{location}/_environment.py")
        assert expected in _environment._installed_via()

    def test_environment_is_frozen(self):
        """It is a snapshot handed to a caller who may put it in a report; nothing downstream
        should be able to edit it after the fact."""
        env = describe_environment()
        with pytest.raises(dataclasses.FrozenInstanceError):
            env.server_version = "9.9.9"    # type: ignore[misc]
        assert isinstance(env, Environment)


class TestEnvironmentIsEverywhereItIsNeeded:
    """The environment has to be reachable without anyone deciding to ask for it.

    `report_a_problem` is the deliberate route, and it only helps somebody who already knows to
    use it. `describe_configuration` is the tool a model calls after ANY refusal, so putting the
    same facts there means they land in the transcript as a side effect of ordinary use - and a
    conversation pasted into an issue then arrives complete.
    """

    def test_describe_configuration_reports_version_and_platform(self):
        settings = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*"})
        server = create_server(lambda: Workspace(FakeBackend()), settings=settings)
        out = asyncio.run(server.call_tool("describe_configuration", {})).structured_content
        assert out["server_version"] == __version__
        assert out["os"] == describe_environment().os
        assert out["python_version"] == platform.python_version()
        assert out["architecture"] and out["installed_via"]

    def test_the_config_resource_names_them_in_its_first_lines(self):
        """Above the policy, because it is the first question asked of any report and the
        cheapest one to answer wrongly from memory."""
        from csa_google_workspace.mcp._resources import render_config
        head = "\n".join(render_config(settings_from_env(
            {"CSA_GW_ALLOWLIST_READ": "*"})).split("\n")[:4])
        env = describe_environment()
        assert env.server_version in head and env.os in head

    def test_the_three_surfaces_agree(self):
        """One source of truth. Three renderings of a version that disagree is worse than one
        that is merely absent, because each looks authoritative on its own."""
        from csa_google_workspace.mcp._resources import render_config
        settings = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*"})
        server = create_server(lambda: Workspace(FakeBackend()), settings=settings)
        report = asyncio.run(server.call_tool("report_a_problem", {})).structured_content
        config = asyncio.run(server.call_tool("describe_configuration", {})).structured_content
        resource = render_config(settings)
        assert report["os"] == config["os"]
        assert report["server_version"] == config["server_version"] == __version__
        assert config["os"] in resource and config["server_version"] in resource

    def test_config_still_carries_no_paths(self):
        """It lists file ids by design, but a filesystem path is a username and is never wanted."""
        settings = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*"})
        server = create_server(lambda: Workspace(FakeBackend()), settings=settings)
        out = asyncio.run(server.call_tool("describe_configuration", {})).structured_content
        for key in ("os", "architecture", "python_version", "installed_via"):
            assert "/Users/" not in str(out[key]) and "C:\\Users" not in str(out[key])


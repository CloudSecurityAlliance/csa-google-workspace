"""`whoami`, `auth_status`, and the client project they both needed (#481, #480).

Before these existed, "is this server logged in, and as whom?" had no direct answer. The only
route was `list_recent_files` plus inference from `"me": true` in `owners` - which costs a real
Drive call, and still cannot tell *not logged in* from *logged in but revoked*.

Tools are called through `server.call_tool`, the SDK's own path, not through `.fn(...)`. The
sibling `csa-google-gmail-calendar` shipped a tool that was unreachable through the real
transport precisely because its tests chose a calling convention the transport never uses.
"""
import asyncio
import json
import os
import pathlib

import pytest

from csa_google_workspace import Workspace, auth
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp._config import Settings
from csa_google_workspace.mcp.server import create_server

DOC = "application/vnd.google-apps.document"
FILES = {"f": {"id": "f", "name": "D", "mimeType": DOC, "webViewLink": "u"}}
RW = auth.scopes_for(False)


def write_token(path, scopes=RW, expiry="2099-01-01T00:00:00"):
    """A cache file shaped like one `Credentials.to_json()` produces."""
    path.write_text(json.dumps({
        "token": "at", "refresh_token": "rt", "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "cid", "client_secret": "cs", "scopes": list(scopes),
        "expiry": expiry,
    }), encoding="utf-8")
    return str(path)


def write_client(path, project_id="csa-drive-docs-mcp"):
    body = {"installed": {"client_id": "587085018288-abc.apps.googleusercontent.com",
                          "client_secret": "GOCSPX-super-secret",
                          "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                          "token_uri": "https://oauth2.googleapis.com/token"}}
    if project_id is not None:
        body["installed"]["project_id"] = project_id
    path.write_text(json.dumps(body), encoding="utf-8")
    return str(path)


def build(backend=None, **settings_kw):
    ws = Workspace(backend if backend is not None else FakeBackend(FILES))
    settings = Settings(**{"token_path": "/nonexistent/token.json", **settings_kw})
    return create_server(lambda: ws, settings=settings)


def call(server, name, **args):
    """Through `server.call_tool` - the SDK's own path, including argument binding and any
    injected parameters - then the structured result, which is what a client receives."""
    return asyncio.run(server.call_tool(name, args)).structured_content


class TestClientProjectId:
    def test_it_reads_the_project_id(self, tmp_path):
        assert auth.client_project_id(write_client(tmp_path / "c.json")) == "csa-drive-docs-mcp"

    @pytest.mark.parametrize("make", [
        pytest.param(lambda p: None, id="no-path-configured"),
        pytest.param(lambda p: str(p / "absent.json"), id="file-absent"),
        pytest.param(lambda p: str(_write(p / "bad.json", "{not json")), id="malformed"),
        pytest.param(lambda p: str(_write(p / "sa.json", '{"type":"service_account"}')),
                     id="not-an-oauth-client"),
        pytest.param(lambda p: write_client(p / "noproj.json", project_id=None),
                     id="client-without-project-id"),
    ])
    def test_it_returns_none_rather_than_raising(self, tmp_path, make):
        """Diagnostic information only. A failure to read it must never break a call that
        would otherwise work, so every unreadable shape is `None`, not an exception."""
        assert auth.client_project_id(make(tmp_path)) is None

    def test_it_never_returns_the_client_secret(self, tmp_path):
        """The reason this reads the file separately instead of reusing `read_client_secrets`:
        that function returns the whole config, `client_secret` included, and anything pulled
        out of it flows from a secret-bearing object to a taint analyser. Only two public
        fields come back from here."""
        fields = auth._public_identity_fields(write_client(tmp_path / "c.json"))
        assert set(fields) == {"client_id", "project_id"}
        assert "GOCSPX-super-secret" not in json.dumps(fields)


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


class TestAuthStatus:
    def test_no_credential_when_nothing_is_cached(self, tmp_path):
        out = call(build(token_path=str(tmp_path / "absent.json")), "auth_status")
        assert out["status"] == "no_credential"
        assert "authenticate" in out["detail"]

    def test_ready_when_the_token_carries_every_scope(self, tmp_path):
        server = build(token_path=write_token(tmp_path / "token.json"))
        assert call(server, "auth_status")["status"] == "ready"

    def test_scope_short_is_its_own_state_not_no_credential(self, tmp_path):
        """The distinction this tool exists for. A credential that IS cached and IS valid, and
        merely predates a scope now required, needs a re-consent - not a first login. Reporting
        `no_credential` would say "you are not logged in" about a token working fine for
        everything it was issued for."""
        path = write_token(tmp_path / "token.json", scopes=auth.scopes_for(True))
        out = call(build(token_path=path, read_only=False), "auth_status")
        assert out["status"] == "scope_short"

    def test_it_reports_the_file_the_read_only_posture_actually_reads(self, tmp_path):
        """`token_path_for`, not the configured path: a read-only posture reads a SEPARATE
        cache (#185). Reporting on a file the server would never open is the one wrong answer
        this tool could give while looking entirely right."""
        out = call(build(token_path=str(tmp_path / "token.json"), read_only=True), "auth_status")
        assert out["token_path"].endswith("token.readonly.json")

    def test_it_makes_no_network_call(self, tmp_path, monkeypatch):
        """The whole point of it existing separately from `load_cached_credentials`, which
        refreshes an expired access token over the wire as part of returning usable creds.

        **The token here is EXPIRED, and that is the entire test.** A fresh one would make this
        pass no matter which function `auth_status` called, because `_refresh` fires only on an
        expired credential - the check would run, prove nothing, and stay green forever. The
        first draft of this test did exactly that.

        The second half proves the instrument: the same fixture put through
        `load_cached_credentials` DOES reach the sentinel. So a green result above means
        `auth_status` took a different path, not that the sentinel was unreachable.
        """
        calls = []
        monkeypatch.setattr(auth, "_refresh", lambda creds: calls.append(creds))
        path = write_token(tmp_path / "token.json", expiry="2020-01-01T00:00:00")

        assert call(build(token_path=path), "auth_status")["status"] == "ready"
        assert calls == [], "auth_status reached the network refresh path"

        auth.load_cached_credentials(path, read_only=False)
        assert len(calls) == 1, ("the sentinel is unreachable, so the assertion above proves "
                                 "nothing - fix this fixture, not the assertion")

    def test_every_state_carries_the_client_project(self, tmp_path):
        """Including the states where there is no usable credential - which is exactly when
        somebody is trying to work out WHICH app they are about to consent to."""
        client = write_client(tmp_path / "c.json")
        absent = call(build(token_path=str(tmp_path / "absent.json"), client_secrets=client),
                      "auth_status")
        ready = call(build(token_path=write_token(tmp_path / "t.json"), client_secrets=client),
                     "auth_status")
        assert absent["client_project"] == "csa-drive-docs-mcp"
        assert ready["client_project"] == "csa-drive-docs-mcp"

    def test_a_tilde_path_is_expanded_the_way_the_loader_expands_it(self, monkeypatch):
        """#490, and it hit the DEFAULT configuration.

        `CSA_GW_TOKEN` defaults to `~/.csa_google_workspace/token.json`. This function used to
        expand the `~` for its existence check and then hand `_read_cached` the raw form -
        which does not expand it, finds nothing, and returns None. Every default install with
        a working credential was told "the credential cached there is not usable. Call
        `authenticate` to log in again."

        It is the exact failure this tool exists to avoid. `auth_status` predicts what
        `load_cached_credentials` would say WITHOUT making its network call; the two
        disagreeing about which file they read makes the prediction worthless while it still
        reads as confident. So the assertion is not "it says ready" - it is that both
        functions agree, against the same path, on the same machine.
        """
        home = pathlib.Path(os.environ["HOME"])
        (home / ".csa_google_workspace").mkdir(parents=True, exist_ok=True)
        write_token(home / ".csa_google_workspace" / "token.json")

        tilde = "~/.csa_google_workspace/token.json"
        out = call(build(token_path=tilde), "auth_status")

        assert out["status"] == "ready"
        # Compared as PATHS, not as strings. `expanduser` substitutes the `~` and leaves
        # the rest of the configured string alone, so on Windows the result keeps the
        # forward slashes it was configured with while `home / ...` produces backslashes -
        # two spellings of one file. The claim is about WHICH FILE is read, and
        # `WindowsPath` equality is what expresses that; on POSIX the two are identical.
        assert pathlib.Path(out["token_path"]) == home / ".csa_google_workspace" / "token.json", \
            "the path reported is the file actually read, not the form it was configured in"
        assert auth.load_cached_credentials(tilde, read_only=False) is not None, \
            "the loader disagrees, so `ready` above proves nothing"

    def test_a_token_that_loads_as_nothing_is_never_reported_ready(self, tmp_path, monkeypatch):
        """`_read_cached` is typed `Credentials | None` and returns None as well as raising -
        today only when the file disappears between the existence check and the read, which is
        a race rather than something a test can stage.

        The branch is kept and pinned anyway, because the wrong answer here is the expensive
        one: every caller reads `ready` as "go ahead and write"."""
        monkeypatch.setattr(auth, "_read_cached", lambda *a, **kw: None)
        out = call(build(token_path=write_token(tmp_path / "token.json")), "auth_status")

        assert out["status"] == "no_credential"
        assert "not usable" in out["detail"]

    def test_client_project_is_none_when_no_client_is_configured(self, tmp_path):
        out = call(build(token_path=str(tmp_path / "absent.json"), client_secrets=None),
                   "auth_status")
        assert out["client_project"] is None


class TestWhoami:
    def test_it_returns_the_signed_in_address(self):
        backend = FakeBackend(FILES, about_user={"emailAddress": "kurt@example.org",
                                                 "displayName": "Kurt"})
        out = call(build(backend), "whoami")
        assert out == {"email_address": "kurt@example.org", "display_name": "Kurt"}

    def test_a_missing_user_node_is_unknown_not_an_empty_address(self):
        """`about.get` answering with no `user` is a real state. Unknown must arrive as `None`
        so a caller can tell "Drive did not say" from "the address is empty" - the latter would
        render as a blank address beside a confident-looking result."""
        out = call(build(FakeBackend(FILES, about_user={})), "whoami")
        assert out == {"email_address": None, "display_name": None}

    def test_it_reads_no_files(self):
        """One `about.get`. If this ever starts touching the file axis, the allowlist becomes
        load-bearing for a question that should not depend on it."""
        backend = FakeBackend(FILES)
        call(build(backend), "whoami")
        # FakeBackend raises KeyError for an unknown file id; a whoami that touched files
        # against an empty allowlist would surface as a policy refusal instead of a result.
        assert call(build(backend), "whoami")["email_address"] == "fake@example.com"

    def test_both_tools_are_annotated_read_only(self):
        by_name = {t.name: t for t in asyncio.run(build().list_tools())}
        assert by_name["whoami"].annotations.read_only_hint is True
        assert by_name["auth_status"].annotations.read_only_hint is True


class TestTheLibraryAnswersWithoutTheServer:
    def test_workspace_whoami_needs_no_mcp_layer(self):
        """The seam rule: the library is callable without the server. `whoami` is a library
        method and the tool is a wrapper, not the other way round."""
        ws = Workspace(FakeBackend(FILES, about_user={"emailAddress": "a@b.c"}))
        assert ws.whoami()["email_address"] == "a@b.c"


class TestLoginNamesTheProject:
    """#480's third bullet: `login` states the project BEFORE opening the browser, so it can be
    checked against the app name on the consent screen about to appear, and again on success
    once that screen is gone."""

    @staticmethod
    def _run(tmp_path, monkeypatch, capsys, project_id="csa-drive-docs-mcp"):
        from csa_google_workspace.mcp import cli
        monkeypatch.setattr("csa_google_workspace.workspace.Workspace.from_oauth",
                            lambda *a, **kw: None)
        client = write_client(tmp_path / "c.json", project_id=project_id)
        code = cli.main(["login"], {"CSA_GW_CLIENT_SECRETS": client,
                                    "CSA_GW_TOKEN": str(tmp_path / "t.json")})
        return code, capsys.readouterr().out

    def test_it_names_the_project_before_the_browser_opens(self, tmp_path, monkeypatch, capsys):
        code, out = self._run(tmp_path, monkeypatch, capsys)
        assert code == 0
        before, after = out.split("Authorized", 1)
        assert "csa-drive-docs-mcp" in before, "the project must be named BEFORE consent"
        assert "csa-drive-docs-mcp" in after, "and again on success, once the screen is gone"

    def test_an_unreadable_project_says_unknown_rather_than_failing(
            self, tmp_path, monkeypatch, capsys):
        """A client file with no `project_id` is unusual, not broken. Diagnostic information
        must never turn a working login into a failed one."""
        code, out = self._run(tmp_path, monkeypatch, capsys, project_id=None)
        assert code == 0
        assert "unknown" in out

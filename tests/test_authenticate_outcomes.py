"""What `authenticate` does AFTER the consent URL is handed over (#481).

`test_mcp_authenticate.py` covers everything up to the elicitation: the shortcut when a token
is already cached, the missing-client message, and a client with no URL-elicitation support.
It stops there, because the existing tests make `elicit_url` raise. That left the three
outcomes a real login actually reaches - **declined**, **timed out**, **authorized** - never
executed, in the one tool that writes a credential to disk.

The loopback is stubbed rather than driven. A real `start_loopback()` binds 127.0.0.1 and
`wait(300.0)` blocks for five minutes with nothing to answer it; the stub also lets each test
assert the listener was CLOSED, which the real one cannot be asked after the fact.
"""
import asyncio
import json

import pytest
from mcp.server.elicitation import AcceptedUrlElicitation, DeclinedElicitation
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from csa_google_workspace import Workspace, exceptions
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp._config import Settings
from csa_google_workspace.mcp.server import create_server

DOC = "application/vnd.google-apps.document"
FILES = {"f": {"id": "f", "name": "D", "mimeType": DOC, "webViewLink": "u"}}
AUTH = "csa_google_workspace.mcp._tools.auth"


class FakeLoopback:
    """Stands in for the listener. Records `close()`, and answers `wait()` from a script."""

    def __init__(self, redirect):
        self.redirect = redirect
        self.closed = False
        self.waited_for = None

    @property
    def redirect_uri_base(self):
        return "http://127.0.0.1:54321/"

    def wait(self, timeout):
        self.waited_for = timeout
        return self.redirect

    def close(self):
        self.closed = True


class FakeSession:
    """`ctx.session` raises outside a real request, and the success path needs one."""

    def __init__(self):
        self.completed = []

    async def send_elicit_complete(self, elicitation_id):
        self.completed.append(elicitation_id)


@pytest.fixture
def flow(monkeypatch, tmp_path):
    """Everything between "no cached token" and the elicitation, stubbed.

    Returns the record of what the tool did, so each test asserts on behaviour rather than on
    the stubs: which URL was elicited, under which id, what `finish` was given, and whether the
    listener was closed.
    """
    record = {"finished": [], "session": FakeSession(), "elicited": []}

    monkeypatch.setattr(f"{AUTH}.load_cached_credentials",
                        lambda tp, ro: (_ for _ in ()).throw(exceptions.AuthError("none")))
    monkeypatch.setattr(f"{AUTH}.build_flow", lambda cs, ro, uri: {"redirect_base": uri})
    monkeypatch.setattr(f"{AUTH}.consent_url", lambda f: "https://accounts.google.com/o/x?s=1")
    monkeypatch.setattr(f"{AUTH}.finish",
                        lambda f, redirect, token_path: record["finished"].append(
                            {"flow": f, "redirect": redirect, "token_path": token_path}))
    monkeypatch.setattr(Context, "session", property(lambda self: record["session"]))

    def install(answer, redirect="http://127.0.0.1:54321/?code=c&state=s"):
        record["loopback"] = FakeLoopback(redirect)
        monkeypatch.setattr(f"{AUTH}.start_loopback", lambda: record["loopback"])

        async def elicit_url(self, *, message, url, elicitation_id):
            record["elicited"].append({"message": message, "url": url, "id": elicitation_id})
            return answer

        monkeypatch.setattr(Context, "elicit_url", elicit_url)

    record["install"] = install
    record["secrets"] = str(tmp_path / "client.json")
    record["token"] = str(tmp_path / "token.json")
    return record


def build(record, **settings_kw):
    settings = Settings(**{"token_path": record["token"],
                           "client_secrets": record["secrets"], **settings_kw})
    return create_server(lambda: Workspace(FakeBackend(FILES)), settings=settings)


def call(server, name, **args):
    return asyncio.run(server.call_tool(name, args)).structured_content


def test_a_declined_elicitation_changes_nothing(flow):
    """Not an error. The user saw the consent prompt and said no, which is a legitimate
    answer - and the reply has to say so plainly, because the alternative is a model that
    reads a failure and tries again."""
    flow["install"](DeclinedElicitation(action="decline"))
    out = call(build(flow), "authenticate")

    assert out["status"] == "declined"
    assert "Nothing changed" in out["detail"]
    assert flow["finished"] == [], "a declined consent must not write a token"
    assert flow["session"].completed == [], "nothing was completed, so nothing to complete"


def test_no_redirect_within_the_window_times_out_rather_than_hanging(flow):
    """`wait` returning None is the browser tab that was opened and never finished. The reply
    names the window, so "nothing happened" is distinguishable from "it broke"."""
    flow["install"](AcceptedUrlElicitation(), redirect=None)
    out = call(build(flow), "authenticate")

    assert out["status"] == "timed_out"
    assert flow["loopback"].waited_for == 300.0
    assert flow["finished"] == [], "no redirect means no token exchange"


def test_a_completed_consent_writes_the_token_and_closes_the_elicitation(flow):
    """The whole point of the tool. Three things have to happen together, and the id is the
    one that is invisible when it goes wrong: the client tracks an open URL elicitation BY
    that id, so completing a different one leaves its authorization prompt open forever."""
    flow["install"](AcceptedUrlElicitation())
    out = call(build(flow), "authenticate")

    assert out["status"] == "authorized"
    assert len(flow["finished"]) == 1
    assert flow["finished"][0]["redirect"] == "http://127.0.0.1:54321/?code=c&state=s"
    assert flow["session"].completed == [flow["elicited"][0]["id"]]


def test_the_flow_is_built_for_the_port_the_listener_actually_bound(flow):
    """The redirect URI in the consent URL and the port being listened on are the same fact
    stated twice. Google redirects to whatever the flow claimed; a mismatch sends the browser
    to a closed port and the login times out with no visible cause."""
    flow["install"](AcceptedUrlElicitation())
    call(build(flow), "authenticate")

    assert flow["finished"][0]["flow"]["redirect_base"] == flow["loopback"].redirect_uri_base


def test_a_read_only_posture_writes_to_the_read_only_cache(flow):
    """`token_path_for`, not `settings.token_path` (#185). A read-only deployment reads a
    SEPARATE cache, so writing the new token to the configured path would leave it somewhere
    nothing ever opens - and CSA_GW_READ_ONLY=1 permanently unsatisfiable, one successful
    login at a time."""
    flow["install"](AcceptedUrlElicitation())
    call(build(flow, read_only=True), "authenticate")

    assert flow["finished"][0]["token_path"].endswith("token.readonly.json")


@pytest.mark.parametrize("answer, redirect", [
    pytest.param(DeclinedElicitation(action="decline"), None, id="declined"),
    pytest.param(AcceptedUrlElicitation(), None, id="timed-out"),
    pytest.param(AcceptedUrlElicitation(), "http://127.0.0.1:54321/?code=c&state=s",
                 id="authorized"),
])
def test_the_listener_is_closed_on_every_outcome(flow, answer, redirect):
    """The `finally`. A loopback left open is a socket on 127.0.0.1 waiting to be handed an
    authorization code, for as long as the server runs - and `authenticate` is the tool a user
    calls repeatedly when something is wrong, so the leak compounds exactly when it is least
    noticed."""
    flow["install"](answer, redirect=redirect)
    call(build(flow), "authenticate")

    assert flow["loopback"].closed


def test_the_listener_is_closed_when_the_client_cannot_elicit(flow):
    """The same guarantee on the raising path, which is the one a client without URL
    elicitation - Claude Desktop today - takes on every single call."""
    flow["install"](AcceptedUrlElicitation())

    async def unsupported(self, **kwargs):
        raise RuntimeError("elicitation/create not supported")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(Context, "elicit_url", unsupported)
        with pytest.raises(ToolError):
            call(build(flow), "authenticate")

    assert flow["loopback"].closed


class TestUnreadableCachedCredential:
    """`auth_status`'s third failure shape: the file is there and cannot be used."""

    def test_a_malformed_token_file_reads_as_no_credential(self, tmp_path):
        """Not `ready`, and not a crash. `status` is what a caller branches on, so a file that
        exists but holds nothing loadable has to arrive as "log in again" - and the detail
        carries the reason, since the status alone would suggest an absent file."""
        path = tmp_path / "token.json"
        path.write_text("{not json", encoding="utf-8")
        out = call(build({"token": str(path), "secrets": None}), "auth_status")

        assert out["status"] == "no_credential"
        assert str(path) in out["detail"] and "could not be read" in out["detail"]

    def test_a_write_token_under_a_read_only_posture_is_refused(self, tmp_path):
        """#185's other half, seen from the status tool: a full-Drive token is REFUSED by a
        read-only deployment rather than accepted and policed in software. It reports as
        `no_credential` - the detail explains why, but the status does not distinguish this
        from an absent file the way `scope_short` distinguishes a stale one. Filed as #488."""
        from csa_google_workspace import auth

        path = tmp_path / "token.readonly.json"
        path.write_text(json.dumps({
            "token": "at", "refresh_token": "rt",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "cid", "client_secret": "cs", "scopes": list(auth.scopes_for(False)),
            "expiry": "2099-01-01T00:00:00"}), encoding="utf-8")
        out = call(build({"token": str(tmp_path / "token.json"), "secrets": None},
                         read_only=True), "auth_status")

        assert out["status"] == "no_credential"
        assert "WRITE scopes" in out["detail"]

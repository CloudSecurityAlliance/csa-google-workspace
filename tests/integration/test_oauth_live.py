"""End-to-end OAuth tests — require a REAL interactive login.

The most opt-in slice of the suite: these drive `auth.py`'s real login, token caching,
and token-file permissions against Google — the paths no FakeBackend test can reach. The
FIRST run opens a browser for consent; later runs reuse the cached token (the default path
`~/.csa_google_workspace/token.json`, shared with the rest of the live suite). Because the
writable login runs first, the read-only test reuses that token and does NOT prompt again.

Gated by CSA_GW_INTEGRATION=1 and CSA_GW_CLIENT_SECRETS.

    CSA_GW_INTEGRATION=1 CSA_GW_CLIENT_SECRETS=path/to/client_secret.json \
        pytest tests/integration/test_oauth_live.py -v
"""
import os
import stat

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CSA_GW_INTEGRATION") != "1",
    reason="set CSA_GW_INTEGRATION=1 (and CSA_GW_CLIENT_SECRETS) to run live OAuth tests",
)

DOC = "application/vnd.google-apps.document"
DEFAULT_TOKEN = os.path.expanduser("~/.csa_google_workspace/token.json")


def _secrets():
    secrets = os.environ.get("CSA_GW_CLIENT_SECRETS")
    if not secrets:
        pytest.skip("set CSA_GW_CLIENT_SECRETS to the OAuth client-secrets JSON path")
    return secrets


def test_from_oauth_login_then_reaches_google():
    """from_oauth() logs in (interactive first run) and the session can reach Google."""
    from csa_google_workspace import Doc, Workspace
    ws = Workspace.from_oauth(_secrets())
    drive = ws._backend._services.drive
    fid = drive.files().create(
        body={"name": "OAUTH-E2E-THROWAWAY", "mimeType": DOC}, fields="id").execute()["id"]
    try:
        d = ws.open(fid)
        assert isinstance(d, Doc)
        assert isinstance(d.as_text(), str)          # a real authenticated read succeeded
    finally:
        drive.files().update(fileId=fid, body={"trashed": True}).execute()


def test_oauth_token_file_not_group_or_world_accessible():
    """auth.py must persist the token with no group/other access, in a private dir."""
    from csa_google_workspace import Workspace
    Workspace.from_oauth(_secrets())                 # ensure a token has been written
    assert os.path.exists(DEFAULT_TOKEN), "expected a cached token after from_oauth()"
    file_mode = stat.S_IMODE(os.stat(DEFAULT_TOKEN).st_mode)
    dir_mode = stat.S_IMODE(os.stat(os.path.dirname(DEFAULT_TOKEN)).st_mode)
    assert file_mode & 0o077 == 0, f"token readable by group/other: {oct(file_mode)}"
    assert dir_mode & 0o077 == 0, f"token dir accessible by group/other: {oct(dir_mode)}"


def test_read_only_oauth_session_reads_but_refuses_writes():
    """A read_only session still reads real content but blocks writes at the client guard."""
    from csa_google_workspace import Workspace
    from csa_google_workspace import exceptions as exc
    ws_rw = Workspace.from_oauth(_secrets())         # writable session creates the fixture
    drive = ws_rw._backend._services.drive
    fid = drive.files().create(
        body={"name": "OAUTH-RO-THROWAWAY", "mimeType": DOC}, fields="id").execute()["id"]
    try:
        ws_ro = Workspace.from_oauth(_secrets(), read_only=True)
        assert ws_ro.read_only is True
        d = ws_ro.open(fid)
        assert isinstance(d.as_text(), str)          # read works under read_only
        with pytest.raises(exc.ReadOnlyError):
            d.append_text("should be blocked")
    finally:
        drive.files().update(fileId=fid, body={"trashed": True}).execute()

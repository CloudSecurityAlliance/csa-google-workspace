"""Interactive OAuth end-to-end suite — SEPARATE from the rest of the tests on purpose.

This is the only suite that needs a **human at a browser** (to grant consent on first run)
and that reads/writes a **very sensitive cached credential** — the OAuth token at
`~/.csa_google_workspace/token.json`, which holds a refresh token. It therefore has its own
opt-in gate, `CSA_GW_OAUTH=1` (distinct from the API-integration suite's
`CSA_GW_INTEGRATION`), and lives in its own directory so it never runs by accident.

It drives `auth.py`'s real login, token caching, and token-file permissions against Google
— the paths no FakeBackend test can reach. The FIRST run opens a browser for consent; later
runs reuse the cached token. The writable login runs first, so the read-only test reuses
that token and does NOT prompt a second time.

    CSA_GW_OAUTH=1 CSA_GW_CLIENT_SECRETS=path/to/client_secret.json \
        pytest tests/oauth -v

Never commit `client_secret.json` or `token*.json` — both are gitignored.
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CSA_GW_OAUTH") != "1",
    reason="set CSA_GW_OAUTH=1 (and CSA_GW_CLIENT_SECRETS) to run the interactive OAuth suite",
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
    """auth.py must persist the token with no group/other access, in a private dir.

    Asked through `auth.file_is_owner_only` rather than `st_mode & 0o077`, because that mask is
    the POSIX SPELLING of the question and this suite is the one place a REAL token gets written.
    On Windows `st_mode` reports 0o666 whatever the file's actual ACL is, so the mask version
    failed on a token that was correctly protected - reporting "your credential is exposed" about
    a file that was not, in the suite a person runs precisely to check that. (#451, #453)

    This suite is gated behind CSA_GW_OAUTH=1, so it was missed when the unit tests were
    converted; nothing unattended could have caught it.
    """
    from csa_google_workspace import Workspace, auth
    Workspace.from_oauth(_secrets())                 # ensure a token has been written
    assert os.path.exists(DEFAULT_TOKEN), "expected a cached token after from_oauth()"
    assert auth.file_is_owner_only(DEFAULT_TOKEN) is True, (
        "the cached token is readable beyond its owner")
    assert auth.file_is_owner_only(os.path.dirname(DEFAULT_TOKEN)) is True, (
        "the token's directory is accessible beyond its owner")


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

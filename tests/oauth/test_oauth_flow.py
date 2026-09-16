r"""Interactive OAuth end-to-end suite — SEPARATE from the rest of the tests on purpose.

This is the only suite that needs a **human at a browser** (to grant consent on first run)
and that reads/writes a **very sensitive cached credential** — the OAuth token at
`~/.csa_google_workspace/token.json`, which holds a refresh token. It therefore has its own
opt-in gate, `CSA_GW_OAUTH=1` (distinct from the API-integration suite's
`CSA_GW_INTEGRATION`), and lives in its own directory so it never runs by accident.

It drives `auth.py`'s real login, token caching, and token-file permissions against Google
— the paths no FakeBackend test can reach. The FIRST run opens a browser for consent; later
runs reuse the cached token.

**EXPECT TWO BROWSER CONSENTS ON A FRESH MACHINE, not one.** This docstring used to say the
writable login runs first "so the read-only test reuses that token and does NOT prompt a second
time". That stopped being true when #185 gave the read-only posture its own cache
(`token.readonly.json`), precisely so the guarantee is *which file exists* rather than a
client-side flag over a full-write token. A read-write token is therefore NOT reused here, by
design - so the read-only test opens a second consent, and with nobody watching it simply hangs
on `run_local_server`. Measured 2026-09-15 on a machine with a valid read-write token.

    # bash / zsh
    CSA_GW_OAUTH=1 CSA_GW_CLIENT_SECRETS=path/to/client_secret.json \
        pytest tests/oauth -v

    # PowerShell - there is NO inline `VAR=x cmd` prefix; set them in the session first
    $env:CSA_GW_OAUTH = "1"
    $env:CSA_GW_CLIENT_SECRETS = "$env:USERPROFILE\.csa_google_workspace\client_secret.json"
    python -m pytest tests/oauth -v

Never commit `client_secret.json` or `token*.json` — both are gitignored.
"""
import contextlib
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CSA_GW_OAUTH") != "1",
    reason="set CSA_GW_OAUTH=1 (and CSA_GW_CLIENT_SECRETS) to run the interactive OAuth suite",
)

DEFAULT_TOKEN = os.path.expanduser("~/.csa_google_workspace/token.json")


def _secrets():
    secrets = os.environ.get("CSA_GW_CLIENT_SECRETS")
    if not secrets:
        pytest.skip("set CSA_GW_CLIENT_SECRETS to the OAuth client-secrets JSON path")
    return secrets


@contextlib.contextmanager
def _throwaway(ws, name):
    """A throwaway Doc, created and trashed THROUGH THE PUBLIC API (#433).

    These tests used to reach `ws._backend._services.drive` and stopped working the day
    `Workspace` began wrapping its backend in `PolicyBackend` unconditionally - that wrapper
    refuses every `_`-prefixed name, which is #82's fail-closed behaviour working as designed.
    Both live tests here errored with `AttributeError: _services`.

    #433 fixed exactly this in `tests/integration/` and **did not reach this file**, because
    this suite is gated behind its own separate flag and nobody ran it. Measured 2026-09-15 on
    a machine with a valid token. Same rule as there: a live suite drives the same surface a
    caller drives, and must not step around the policy layer it runs under.
    """
    ref = ws.files.create(name, "document")
    try:
        yield ref.id
    finally:
        ws.files.trash(ref.id)


def test_from_oauth_login_then_reaches_google():
    """from_oauth() logs in (interactive first run) and the session can reach Google."""
    from csa_google_workspace import Doc, Workspace
    ws = Workspace.from_oauth(_secrets())
    with _throwaway(ws, "OAUTH-E2E-THROWAWAY") as fid:
        d = ws.open(fid)
        assert isinstance(d, Doc)
        assert isinstance(d.as_text(), str)          # a real authenticated read succeeded


def test_oauth_token_file_not_group_or_world_accessible():
    """The real cached token must not be readable beyond its owner.

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


def test_a_token_directory_we_create_is_private(tmp_path):
    """The directory half - and it is a DIFFERENT claim, which is why it is a different test.

    `_write_token` hardens a directory **only when it created it**, and mutating a
    caller-supplied one is a side effect audit finding #4 says not to have. So asserting the
    REAL `~/.csa_google_workspace` is owner-only tests the user's filesystem, not this code:
    measured on a live machine 2026-09-15, that directory already existed (it held
    `client_secret.json`), so it correctly inherits its own permissions and the assertion
    would fail while everything worked as designed.

    That is the same false-alarm shape this file was just fixed for, one level along - so the
    claim is narrowed to the one the code actually makes, and pointed at a directory we own.
    The token FILE is what carries the guarantee either way, and the test above asserts it.
    """
    from csa_google_workspace import auth
    token = tmp_path / "made-by-us" / "token.json"
    auth._write_token(str(token), _FakeCreds())
    assert auth.file_is_owner_only(str(token.parent)) is True
    assert auth.file_is_owner_only(str(token)) is True


class _FakeCreds:
    def to_json(self):
        return '{"token": "not-a-real-token"}'


def test_read_only_oauth_session_reads_but_refuses_writes():
    """A read_only session still reads real content but blocks writes at the client guard."""
    from csa_google_workspace import Workspace
    from csa_google_workspace import exceptions as exc
    ws_rw = Workspace.from_oauth(_secrets())         # writable session creates the fixture
    with _throwaway(ws_rw, "OAUTH-RO-THROWAWAY") as fid:
        ws_ro = Workspace.from_oauth(_secrets(), read_only=True)
        assert ws_ro.read_only is True
        d = ws_ro.open(fid)
        assert isinstance(d.as_text(), str)          # read works under read_only
        with pytest.raises(exc.ReadOnlyError):
            d.append_text("should be blocked")

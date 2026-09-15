"""Offline coverage for the OAuth credential lifecycle + token-file hardening
(audit finding #3). load_credentials was previously only exercised by the gated,
browser-driven tests/oauth/ suite, so a regression widening the token-file mode or
breaking the cache/reconsent/refresh branching would ship green. These monkeypatch
the Google objects and use a real tmp_path token file — no browser, no network.
"""
import os

import pytest

from csa_google_workspace import auth
from csa_google_workspace.exceptions import AuthError


class FakeCreds:
    def __init__(self, *, valid=True, expired=False, refresh_token="rt", scopes=None):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self.scopes = auth.scopes_for(read_only=False) if scopes is None else scopes
        self.refreshed = False

    def refresh(self, request):
        self.refreshed = True
        self.valid = True

    def to_json(self):
        return '{"token": "fake"}'


class FakeFlow:
    def __init__(self, creds):
        self.creds = creds

    def run_local_server(self, port=0):
        return self.creds


def _no_flow(*args, **kwargs):
    raise AssertionError("the interactive OAuth flow should not run on this path")


def _patch_from_file(monkeypatch, creds_or_exc):
    def loader(path, *a, **k):
        if isinstance(creds_or_exc, Exception):
            raise creds_or_exc
        return creds_or_exc
    monkeypatch.setattr(auth.Credentials, "from_authorized_user_file", loader)


def _client_secrets(tmp_path, encoding="utf-8"):
    """A real client-secrets file on disk, because `load_credentials` now reads it itself.

    It used to hand the path straight to `from_client_secrets_file`, so the literal string
    "client.json" was enough. Since #449 we parse it ourselves - to tolerate a UTF-8 BOM and to
    fail with a message naming the file - which means these tests exercise the real reader
    rather than a mock standing in for it. That is the better trade: one less mock, and the
    consent branch is now proven against a file that actually parses.
    """
    p = tmp_path / "client_secret.json"
    p.write_text('{"installed":{"client_id":"cid","client_secret":"cs",'
                 '"auth_uri":"https://accounts.google.com/o/oauth2/auth",'
                 '"token_uri":"https://oauth2.googleapis.com/token"}}', encoding=encoding)
    return str(p)


def _patch_flow(monkeypatch, creds):
    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_config",
                        lambda config, scopes: FakeFlow(creds))


def test_valid_cached_token_is_returned_without_flow(tmp_path, monkeypatch):
    token = tmp_path / "token.json"
    token.write_text("{}")
    cached = FakeCreds(valid=True)
    _patch_from_file(monkeypatch, cached)
    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_secrets_file", _no_flow)

    assert auth.load_credentials("client.json", str(token), read_only=False) is cached


def test_expired_token_is_refreshed_not_reauthorized(tmp_path, monkeypatch):
    token = tmp_path / "token.json"
    token.write_text("{}")
    creds = FakeCreds(valid=False, expired=True, refresh_token="rt")
    _patch_from_file(monkeypatch, creds)
    monkeypatch.setattr(auth, "Request", lambda: None)
    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_secrets_file", _no_flow)

    result = auth.load_credentials("client.json", str(token), read_only=False)
    assert result is creds and creds.refreshed is True


def test_missing_token_triggers_oauth_flow(tmp_path, monkeypatch):
    token = tmp_path / "sub" / "token.json"   # neither file nor dir exists yet
    fresh = FakeCreds(valid=True)
    _patch_flow(monkeypatch, fresh)

    result = auth.load_credentials(_client_secrets(tmp_path), str(token), read_only=False)
    assert result is fresh and token.exists()


def test_insufficient_scopes_forces_reconsent(tmp_path, monkeypatch):
    token = tmp_path / "token.json"
    token.write_text("{}")
    stale = FakeCreds(valid=True, scopes=[s for s in auth.scopes_for(False) if "presentations" not in s])
    _patch_from_file(monkeypatch, stale)
    fresh = FakeCreds(valid=True)
    _patch_flow(monkeypatch, fresh)

    # the cached token lacks a required scope -> discarded, re-consented
    assert auth.load_credentials(_client_secrets(tmp_path), str(token),
                                 read_only=False) is fresh


def test_written_token_and_dir_are_owner_only(tmp_path, monkeypatch):
    token = tmp_path / "creds" / "token.json"   # dir is created by load_credentials
    _patch_flow(monkeypatch, FakeCreds(valid=True))

    auth.load_credentials(_client_secrets(tmp_path), str(token), read_only=False)

    # Asked as a question, not asserted as 0o600. `chmod` is a no-op on Windows, so the mode
    # literal answered 0o666 forever there while the file was genuinely unprotected - the
    # assertion certified nothing on the platform that needed it most.
    assert auth.file_is_owner_only(str(token)) is True
    assert auth.file_is_owner_only(str(token.parent)) is True


def test_corrupt_cached_token_raises_auth_error(tmp_path, monkeypatch):
    token = tmp_path / "token.json"
    token.write_text("{}")
    _patch_from_file(monkeypatch, ValueError("malformed token file"))

    with pytest.raises(auth.AuthError):
        auth.load_credentials("client.json", str(token), read_only=False)


# --- #52 interim token.json hardening -----------------------------------------

def test_existing_token_file_mode_is_enforced(tmp_path, monkeypatch):
    """#17: O_TRUNC keeps a pre-existing file's mode, so fchmod must re-tighten to 0o600."""
    token = tmp_path / "token.json"
    token.write_text("old")
    if os.name != "nt":
        token.chmod(0o644)                                   # pre-existing, world-readable
    _patch_from_file(monkeypatch, FakeCreds(valid=False, expired=False, refresh_token=None))
    _patch_flow(monkeypatch, FakeCreds(valid=True))          # falls through to (re)write
    auth.load_credentials(_client_secrets(tmp_path), str(token), read_only=False)
    assert auth.file_is_owner_only(str(token)) is True


def test_preexisting_token_dir_is_not_chmodded(tmp_path, monkeypatch):
    """#4: a caller-supplied existing dir must not have its mode mutated as a side effect."""
    d = tmp_path / "caller-dir"
    d.mkdir()
    if os.name != "nt":
        d.chmod(0o755)
    token = d / "token.json"
    before = auth.file_is_owner_only(str(d))
    _patch_flow(monkeypatch, FakeCreds(valid=True))
    auth.load_credentials(_client_secrets(tmp_path), str(token), read_only=False)
    assert auth.file_is_owner_only(str(d)) == before         # unchanged, not hardened for them
    assert auth.file_is_owner_only(str(token)) is True       # the file we created is hardened


def test_symlinked_token_path_is_refused(tmp_path, monkeypatch):
    """#17: O_NOFOLLOW must refuse to write through a symlink at the token path."""
    link = tmp_path / "token.json"
    try:
        link.symlink_to(tmp_path / "nonexistent-target.json")  # dangling -> reaches the write
    except (OSError, NotImplementedError):                     # Windows needs Developer Mode
        pytest.skip("this platform will not create a symlink without elevation; the explicit "
                    "check is covered by tests/test_token_hardening_is_platform_honest.py")
    _patch_flow(monkeypatch, FakeCreds(valid=True))
    with pytest.raises(OSError):
        auth.load_credentials(_client_secrets(tmp_path), str(link), read_only=False)


def test_corrupt_token_error_does_not_leak_cause(tmp_path, monkeypatch):
    """#19: the underlying auth-library error string must not be interpolated into AuthError."""
    token = tmp_path / "token.json"
    token.write_text("{}")
    _patch_from_file(monkeypatch, ValueError("SENSITIVE token material"))
    with pytest.raises(auth.AuthError) as ei:
        auth.load_credentials("client.json", str(token), read_only=False)
    assert "SENSITIVE token material" not in str(ei.value)   # not in the message
    assert ei.value.__cause__ is not None                    # but preserved via `from e`


# --- load_cached_credentials: the non-interactive half (MCP server, spec §5) ---
#
# The MCP server runs under stdio, where stdout is the JSON-RPC channel and
# InstalledAppFlow.run_local_server() would both print() into it and block on a
# browser redirect. So the server must never reach the interactive branch. Rather
# than rely on discipline, the branch is absent from the function it calls: every
# test below patches InstalledAppFlow to _no_flow, so reaching it fails loudly.

def test_cached_valid_token_is_returned(tmp_path, monkeypatch):
    token = tmp_path / "token.json"
    token.write_text("{}")
    cached = FakeCreds(valid=True)
    _patch_from_file(monkeypatch, cached)
    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_secrets_file", _no_flow)

    assert auth.load_cached_credentials(str(token), read_only=False) is cached


def test_cached_expired_token_is_refreshed_and_persisted(tmp_path, monkeypatch):
    token = tmp_path / "token.json"
    token.write_text("{}")
    creds = FakeCreds(valid=False, expired=True, refresh_token="rt")
    _patch_from_file(monkeypatch, creds)
    monkeypatch.setattr(auth, "Request", lambda: None)
    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_secrets_file", _no_flow)

    result = auth.load_cached_credentials(str(token), read_only=False)
    assert result is creds and creds.refreshed is True
    assert token.read_text() == '{"token": "fake"}'          # refreshed token persisted
    assert auth.file_is_owner_only(str(token)) is True       # and still owner-only


def test_cached_missing_token_raises_rather_than_prompting(tmp_path, monkeypatch):
    token = tmp_path / "sub" / "token.json"                  # neither file nor dir exists
    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_secrets_file", _no_flow)

    with pytest.raises(auth.AuthError):
        auth.load_cached_credentials(str(token), read_only=False)


def test_cached_insufficient_scopes_raises_rather_than_reconsenting(tmp_path, monkeypatch):
    token = tmp_path / "token.json"
    token.write_text("{}")
    stale = FakeCreds(valid=True, scopes=[s for s in auth.scopes_for(False) if "presentations" not in s])
    _patch_from_file(monkeypatch, stale)
    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_secrets_file", _no_flow)

    with pytest.raises(auth.AuthError):
        auth.load_cached_credentials(str(token), read_only=False)


def test_cached_unrefreshable_token_raises(tmp_path, monkeypatch):
    """Not valid and no refresh token: load_credentials would re-consent here; this must not."""
    token = tmp_path / "token.json"
    token.write_text("{}")
    _patch_from_file(monkeypatch, FakeCreds(valid=False, expired=False, refresh_token=None))
    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_secrets_file", _no_flow)

    with pytest.raises(auth.AuthError):
        auth.load_cached_credentials(str(token), read_only=False)


def test_cached_corrupt_token_error_does_not_leak_cause(tmp_path, monkeypatch):
    token = tmp_path / "token.json"
    token.write_text("{}")
    _patch_from_file(monkeypatch, ValueError("SENSITIVE token material"))
    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_secrets_file", _no_flow)

    with pytest.raises(auth.AuthError) as ei:
        auth.load_cached_credentials(str(token), read_only=False)
    assert "SENSITIVE token material" not in str(ei.value)
    assert ei.value.__cause__ is not None


def test_a_cached_read_write_token_is_REFUSED_for_a_read_only_request(tmp_path, monkeypatch):
    """CHANGED in 0.30.2 (#185). This asserted the opposite - that a cached read-write token
    serves a `read_only=True` load - which is what made `CSA_GW_READ_ONLY=1` a client-side
    `Policy` over a full-Drive credential rather than a narrower one.

    Two things now stop it, and this test exercises the second: read-only consent is cached in
    its own file (`token.readonly.json`), and a token carrying write scopes is refused outright
    even if it is found at that path.

    `needs_reconsent` still says a write scope satisfies a read requirement, which is true of
    OAuth and is asserted in tests/test_auth.py. What changed is the posture's policy, not that
    fact.
    """
    token = tmp_path / "token.readonly.json"      # the path a read-only posture looks at
    token.write_text("{}")
    rw = FakeCreds(valid=True, scopes=auth.scopes_for(read_only=False))
    _patch_from_file(monkeypatch, rw)
    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_secrets_file", _no_flow)

    with pytest.raises(AuthError) as e:
        auth.load_cached_credentials(str(tmp_path / "token.json"), read_only=True)
    assert "write" in str(e.value).lower()


def test_a_read_write_request_still_uses_the_unsuffixed_cache(tmp_path, monkeypatch):
    """The counterweight: separating the caches must not disturb the default posture."""
    token = tmp_path / "token.json"
    token.write_text("{}")
    rw = FakeCreds(valid=True, scopes=auth.scopes_for(read_only=False))
    _patch_from_file(monkeypatch, rw)
    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_secrets_file", _no_flow)

    assert auth.load_cached_credentials(str(token), read_only=False) is rw

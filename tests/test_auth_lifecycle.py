"""Offline coverage for the OAuth credential lifecycle + token-file hardening
(audit finding #3). load_credentials was previously only exercised by the gated,
browser-driven tests/oauth/ suite, so a regression widening the token-file mode or
breaking the cache/reconsent/refresh branching would ship green. These monkeypatch
the Google objects and use a real tmp_path token file — no browser, no network.
"""
import os
import stat

import pytest

from csa_google_workspace import auth


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


def _patch_flow(monkeypatch, creds):
    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_secrets_file",
                        lambda secrets, scopes: FakeFlow(creds))


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

    result = auth.load_credentials("client.json", str(token), read_only=False)
    assert result is fresh and token.exists()


def test_insufficient_scopes_forces_reconsent(tmp_path, monkeypatch):
    token = tmp_path / "token.json"
    token.write_text("{}")
    stale = FakeCreds(valid=True, scopes=[s for s in auth.scopes_for(False) if "presentations" not in s])
    _patch_from_file(monkeypatch, stale)
    fresh = FakeCreds(valid=True)
    _patch_flow(monkeypatch, fresh)

    # the cached token lacks a required scope -> discarded, re-consented
    assert auth.load_credentials("client.json", str(token), read_only=False) is fresh


def test_written_token_and_dir_are_owner_only(tmp_path, monkeypatch):
    token = tmp_path / "creds" / "token.json"   # dir is created by load_credentials
    _patch_flow(monkeypatch, FakeCreds(valid=True))

    auth.load_credentials("client.json", str(token), read_only=False)

    assert stat.S_IMODE(os.stat(token).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(token.parent).st_mode) == 0o700


def test_corrupt_cached_token_raises_auth_error(tmp_path, monkeypatch):
    token = tmp_path / "token.json"
    token.write_text("{}")
    _patch_from_file(monkeypatch, ValueError("malformed token file"))

    with pytest.raises(auth.AuthError):
        auth.load_credentials("client.json", str(token), read_only=False)

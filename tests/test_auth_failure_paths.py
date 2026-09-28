"""Two `auth.py` failure paths that were reachable and untested.

Both are the credential path, and both turn somebody else's exception into this project's own
`AuthError` - which is the whole reason they exist. An untested translation layer is one that
reports the wrong thing on the day it runs.
"""
import pytest
from google.auth.exceptions import GoogleAuthError

from csa_google_workspace import auth
from csa_google_workspace.exceptions import AuthError


class TestRefreshFailureBecomesAuthError:
    """`_refresh` wraps `creds.refresh()`. A refresh fails for ordinary reasons - a revoked
    grant, a deleted OAuth client, no network - and the caller needs one error type, not
    google-auth's."""

    @pytest.mark.parametrize("raised", [
        GoogleAuthError("invalid_grant: token revoked"),
        ValueError("malformed token response"),
    ])
    def test_both_upstream_error_types_are_translated(self, raised):
        class _Creds:
            def refresh(self, _request):
                raise raised

        with pytest.raises(AuthError, match="could not refresh cached credentials"):
            auth._refresh(_Creds())

    def test_the_original_is_kept_as_the_cause(self):
        """`from e`, not a bare raise: "could not refresh" alone does not say whether the grant
        was revoked or the network was down, and those have different remedies."""
        original = GoogleAuthError("invalid_grant")

        class _Creds:
            def refresh(self, _request):
                raise original

        with pytest.raises(AuthError) as ei:
            auth._refresh(_Creds())
        assert ei.value.__cause__ is original


class TestLoadCachedCredentialsWithNothingLoadable:
    def test_it_raises_rather_than_returning_none(self, tmp_path, monkeypatch):
        """`_read_cached` returns None for "nothing loadable" and RAISES for a scope-short
        token, so a None here means only the first. The caller is asking for usable credentials,
        so the honest answer is an error - returning None would push the decision onto every
        call site and they do not all check."""
        # The file must EXIST: an earlier guard raises "no cached credentials" for a missing
        # one, which is a different state with a different remedy (log in, versus log in again).
        # Without this the test passes through a branch it was not written for.
        token = tmp_path / "token.json"
        token.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(auth, "_read_cached", lambda *a, **kw: None)

        with pytest.raises(AuthError, match="no usable cached credentials"):
            auth.load_cached_credentials(str(token), read_only=False)

    def test_a_missing_file_is_a_different_error(self, tmp_path):
        """The state above is "a token is there and unusable". This one is "there is no token".
        Same remedy word, different situation, and collapsing them would have hidden the fact
        that the test above was never reaching its branch."""
        with pytest.raises(AuthError, match="no cached credentials"):
            auth.load_cached_credentials(str(tmp_path / "absent.json"), read_only=False)

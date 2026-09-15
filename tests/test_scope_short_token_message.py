"""A token that exists and is one scope short is not "no token".

**Found live, 2026-08-31**, on the first install to upgrade across v0.34.0. The message said:

    Not authorized to reach Google yet (cached credentials lack the required scopes).
    No usable token at ~/.csa_google_workspace/token.json.

Both clauses at once, and the second was **false** — the token was sitting there, valid, with
its original four scopes. It was one short, because v0.34.0 added `drive.labels.readonly`.

**Why this state is new rather than rare.** Every earlier re-consent was a fresh install or an
expiry, and "no usable token" was true for both. v0.34.0 is the first release where an existing,
working token became insufficient — and every future scope addition does it again. So the
sentence had never been wrong before, and would have been wrong every time from now on.

Two consequences a reader acts on, which is why this is worth a test rather than a reword:

1. **"No token" sends you looking for a missing file** — or makes you think a login was lost —
   when the fix is a re-consent of a login that is fine.
2. **`login` may not be enough.** A plain `login` can find a loadable token and decline to do
   anything; the scope-short case needs `--force`. Telling somebody to run the command that
   no-ops is worse than telling them nothing.
"""
from __future__ import annotations

import pytest

from csa_google_workspace import auth
from csa_google_workspace.mcp._config import unauthorized_message


class TestTheMessageLooksInsteadOfAsserting:
    def test_a_present_token_is_not_described_as_absent(self, tmp_path):
        token = tmp_path / "token.json"
        token.write_text("{}")
        msg = unauthorized_message(str(token), "cached credentials lack 1 required scope(s)")
        assert "No token at" not in msg, "the file is right there"
        assert "present but not sufficient" in msg

    def test_an_absent_token_still_says_so(self, tmp_path):
        """The original wording was right for this case, and must survive."""
        msg = unauthorized_message(str(tmp_path / "nope.json"), "no usable cached credentials")
        assert "No token at" in msg
        assert "present but not sufficient" not in msg

    def test_a_present_token_gets_login_force(self, tmp_path):
        """A plain `login` can see a loadable token and decline to act, so the instruction for
        this case has to be the one that actually re-consents."""
        token = tmp_path / "token.json"
        token.write_text("{}")
        assert "login --force" in unauthorized_message(str(token), "scopes")

    def test_an_absent_token_gets_plain_login(self, tmp_path):
        """`--force` on a first login is noise, and noise in a first-run message costs trust."""
        msg = unauthorized_message(str(tmp_path / "nope.json"), "no credentials")
        assert "login" in msg and "--force" not in msg

    def test_it_still_offers_the_no_terminal_path_first(self, tmp_path):
        """The property the docstring calls (a). Both branches keep it."""
        for path in (tmp_path / "nope.json", tmp_path / "token.json"):
            if path.name == "token.json":
                path.write_text("{}")
            msg = unauthorized_message(str(path), "x")
            assert msg.index("authenticate") < msg.index("terminal")

    def test_it_still_tells_the_model_not_to_go_hunting(self, tmp_path):
        """Recorded as having actually happened: a capable model given only "no credentials"
        starts searching the filesystem for token files."""
        msg = unauthorized_message(str(tmp_path / "nope.json"), "x")
        assert "do not try to locate or read credential files" in msg.lower()

    def test_a_tilde_path_is_resolved_before_looking(self, tmp_path, monkeypatch):
        """The real path is `~/.csa_google_workspace/token.json`. Checking existence without
        expanding the tilde would report every real install as having no token — which is the
        exact bug, reintroduced one layer down."""
        # BOTH, because `expanduser` reads a different variable per platform: posixpath
        # uses HOME, ntpath uses USERPROFILE and never consults HOME at all. Setting only
        # HOME left `~` resolving to the real profile on Windows, so this test compared a
        # developer's actual home against tmp_path. (#453)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        home_token = tmp_path / ".csa_google_workspace" / "token.json"
        home_token.parent.mkdir(parents=True)
        home_token.write_text("{}")
        msg = unauthorized_message("~/.csa_google_workspace/token.json", "scopes")
        assert "present but not sufficient" in msg


class TestTheErrorNamesTheMissingScopes:
    def test_it_says_which_scope_is_missing(self):
        e = auth.ScopesMissingError(
            ["https://www.googleapis.com/auth/drive.labels.readonly"])
        assert "drive.labels.readonly" in str(e)

    def test_it_says_how_many(self):
        e = auth.ScopesMissingError(["a/one", "b/two"])
        assert "2 required scope(s)" in str(e)
        assert "one" in str(e) and "two" in str(e)

    def test_it_says_this_is_a_reconsent_not_a_lost_login(self):
        """The sentence that stops somebody debugging the wrong problem."""
        e = auth.ScopesMissingError(["x/y"])
        assert "re-consent, not a lost login" in str(e)

    def test_it_keeps_the_scopes_available_to_a_caller(self):
        """A message is for a human; the list is for anything that wants to act on it."""
        e = auth.ScopesMissingError(["x/a", "y/b"])
        assert e.scopes == ["x/a", "y/b"]

    def test_it_is_an_AuthError(self):
        """Existing `except AuthError` handlers must keep working — this narrows the type
        without changing what anybody catches."""
        assert isinstance(auth.ScopesMissingError(["x"]), auth.AuthError)


class TestTheTwoCallersStillWantOppositeThings:
    def test_the_non_interactive_path_raises_with_detail(self, tmp_path, monkeypatch):
        """The stdio server cannot prompt, so the shortfall has to become a message."""
        token = tmp_path / "token.json"
        token.write_text("{}")

        class _Creds:
            scopes = [s for s in auth.scopes_for(False) if "labels" not in s]
            valid = True
        monkeypatch.setattr(auth.Credentials, "from_authorized_user_file",
                            staticmethod(lambda p: _Creds()))

        with pytest.raises(auth.ScopesMissingError) as e:
            auth.load_cached_credentials(str(token), read_only=False)
        assert "drive.labels.readonly" in str(e.value)

    def test_the_interactive_path_still_falls_through_to_consent(self, tmp_path, monkeypatch):
        """It CAN prompt, so a scope-short token means "go and get consent" — not an error.
        Raising here was a regression introduced while fixing the message, caught by
        tests/test_auth_lifecycle.py, and this pins the distinction rather than the accident."""
        token = tmp_path / "token.json"
        token.write_text("{}")

        class _Stale:
            scopes = [s for s in auth.scopes_for(False) if "labels" not in s]
            valid = True

        class _Fresh:
            valid = True
            def to_json(self): return "{}"

        fresh = _Fresh()
        monkeypatch.setattr(auth.Credentials, "from_authorized_user_file",
                            staticmethod(lambda p: _Stale()))
        monkeypatch.setattr(
            auth.InstalledAppFlow, "from_client_config",
            staticmethod(lambda *a, **k: type("F", (), {
                "run_local_server": lambda self, **kw: fresh})()))

        # A real file on disk: `load_credentials` parses it itself since #449.
        secrets = tmp_path / "client_secret.json"
        secrets.write_text('{"installed":{"client_id":"cid","client_secret":"cs"}}',
                           encoding="utf-8")
        assert auth.load_credentials(str(secrets), str(token), read_only=False) is fresh

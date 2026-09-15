"""PKCE is asked for, and a stray request cannot consume the OAuth redirect.

**T28 — PKCE was inherited, not requested.** `build_flow` never passed `code_verifier` or
`autogenerate_code_verifier`, so PKCE S256 was active only because
`google-auth-oauthlib`'s default happens to be on.

Worth being precise, because the audit's stated rationale for this did not hold and the fix is
narrower than it proposed. It suggested the `>=1.0` floor *"admits releases where the default is
off"*; downloading the sdists showed **1.0.0 already defaults it on**, as do 1.2.0 and 1.4.1. So
raising the floor was not done and would have bought nothing.

What is real is the *inheritance*: a security property we depend on, that nothing in this
codebase asks for and no test observes. A future release flipping that default would be silent.
Asking explicitly costs one keyword and turns an assumption into a statement — and unlike a
version bound, it constrains what the code **does** rather than what may be **installed**.

**T30 — the one-shot collector consumed any request.** The WSGI app recorded
`request_uri(environ)` and set `arrived` for **any path and any method**, with no test for
`code` or `state`, and the server served exactly one request. So any local process scanning
`127.0.0.1`, or any page issuing a cross-origin GET during the 300-second window, consumed the
listener and the real redirect was refused. **A stray browser `/favicon.ico` fetch does it by
accident.**

Availability only — `state` and PKCE still prevent a forged code being exchanged, so this is not
a path to a token. It is a path to a login that fails for reasons nobody can diagnose.
"""
from __future__ import annotations

import threading
import urllib.error
import urllib.request

from csa_google_workspace.mcp import _auth_flow


class TestPkceIsRequestedRatherThanInherited:
    def test_pkce_is_passed_explicitly_not_left_to_the_default(self, tmp_path, monkeypatch):
        """Asserting `flow.autogenerate_code_verifier is True` would NOT test this — it is the
        dependency's default, so that assertion passes whether or not we ask. The finding is
        precisely that we were relying on the default, so the test has to observe the CALL.

        Written after the attribute version passed against the unfixed code.
        """
        import google_auth_oauthlib.flow as gaf

        seen = {}
        # The spy follows the call: since #449 we read the file ourselves and hand a parsed
        # config to `from_client_config`, so watching `from_client_secrets_file` would watch a
        # call that no longer happens and pass vacuously - the exact failure this test's own
        # docstring warns about one layer down.
        original = gaf.Flow.from_client_config.__func__

        def spy(cls, config, scopes=None, **kwargs):
            seen.update(kwargs)
            return original(cls, config, scopes=scopes, **kwargs)

        monkeypatch.setattr(gaf.Flow, "from_client_config", classmethod(spy))
        secrets = tmp_path / "client_secret.json"
        secrets.write_text(
            '{"installed":{"client_id":"cid","client_secret":"cs",'
            '"auth_uri":"https://accounts.google.com/o/oauth2/auth",'
            '"token_uri":"https://oauth2.googleapis.com/token"}}', encoding="utf-8")
        _auth_flow.build_flow(str(secrets), read_only=False,
                              redirect_uri="http://127.0.0.1:1/")
        assert seen.get("autogenerate_code_verifier") is True, (
            f"PKCE was not requested; kwargs passed were {seen}. It works today only because "
            f"the dependency defaults it on, which is the finding.")

    def test_the_consent_url_carries_s256(self, tmp_path):
        """The observable end of it. A default that silently changed would fail here rather
        than in production, which is the whole point of asserting it."""
        secrets = tmp_path / "client_secret.json"
        secrets.write_text(
            '{"installed":{"client_id":"cid","client_secret":"cs",'
            '"auth_uri":"https://accounts.google.com/o/oauth2/auth",'
            '"token_uri":"https://oauth2.googleapis.com/token"}}', encoding="utf-8")
        flow = _auth_flow.build_flow(str(secrets), read_only=False,
                                     redirect_uri="http://127.0.0.1:1/")
        url = _auth_flow.consent_url(flow)
        assert "code_challenge=" in url
        assert "code_challenge_method=S256" in url, (
            "plain PKCE is not PKCE; S256 is the part that matters")


class TestAStrayRequestCannotConsumeTheRedirect:
    """Each test drives a real loopback on 127.0.0.1, because the defect is in how the server
    handles requests and a mocked `environ` would not exercise it."""

    @staticmethod
    def _get(port, path):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3).read()
        except (urllib.error.URLError, OSError):
            pass

    def test_a_favicon_fetch_does_not_consume_it(self):
        """The accidental case, and the likeliest: a browser fetching /favicon.ico while the
        consent tab is open."""
        loop = _auth_flow.start_loopback()
        try:
            self._get(loop.port, "/favicon.ico")
            assert not loop._collector.arrived.is_set(), (
                "a favicon fetch consumed the OAuth listener")
            self._get(loop.port, "/?code=abc&state=xyz")
            assert loop._collector.arrived.wait(3), "the real redirect was not accepted"
            assert "code=abc" in (loop._collector.redirect_uri or "")
        finally:
            loop._server.server_close()

    def test_a_bare_scan_does_not_consume_it(self):
        loop = _auth_flow.start_loopback()
        try:
            self._get(loop.port, "/")
            assert not loop._collector.arrived.is_set()
            self._get(loop.port, "/?code=abc&state=xyz")
            assert loop._collector.arrived.wait(3)
        finally:
            loop._server.server_close()

    def test_several_strays_in_a_row_still_leave_it_listening(self):
        """One-shot handling meant the FIRST stray won. Serving in a loop is the fix, and a
        loop that gives up after N would just move the number."""
        loop = _auth_flow.start_loopback()
        try:
            for path in ("/favicon.ico", "/", "/robots.txt", "/.well-known/x", "/?foo=1"):
                self._get(loop.port, path)
            assert not loop._collector.arrived.is_set()
            self._get(loop.port, "/?code=abc&state=xyz")
            assert loop._collector.arrived.wait(3)
        finally:
            loop._server.server_close()

    def test_an_error_redirect_is_accepted(self):
        """Google sends `?error=access_denied&state=...` when the user clicks Cancel. That is a
        real answer and must end the wait - otherwise a declined consent hangs for the full
        timeout with nothing on screen explaining why."""
        loop = _auth_flow.start_loopback()
        try:
            self._get(loop.port, "/?error=access_denied&state=xyz")
            assert loop._collector.arrived.wait(3), (
                "a user clicking Cancel must not leave the listener waiting")
        finally:
            loop._server.server_close()

    def test_the_success_page_is_still_served_to_the_real_redirect(self):
        loop = _auth_flow.start_loopback()
        try:
            body = urllib.request.urlopen(
                f"http://127.0.0.1:{loop.port}/?code=abc&state=xyz", timeout=3).read()
            assert b"<" in body and len(body) > 100, "the branded success page is gone"
        finally:
            loop._server.server_close()

    def test_a_stray_gets_a_response_rather_than_a_hang(self):
        """Ignoring a request must not mean leaving the socket open: a scanner that hangs is a
        scanner still holding a connection to a listener waiting for a credential."""
        loop = _auth_flow.start_loopback()
        try:
            done = threading.Event()

            def hit():
                self._get(loop.port, "/favicon.ico")
                done.set()

            threading.Thread(target=hit, daemon=True).start()
            assert done.wait(5), "a stray request hung instead of being answered"
        finally:
            loop._server.server_close()


class TestClosingTheListenerIsQuiet:
    """The serve loop must not leave an exception in its thread when the caller shuts it down.

    Introduced while fixing T30 and caught by pytest's unhandled-thread-exception warning:
    `server_close()` sets the descriptor to -1, and `handle_request()` then fails inside
    `selectors` with `ValueError: Invalid file descriptor: -1` — **not** an `OSError**, so the
    original `except OSError` missed it. Invisible in normal use, and noise in any log that
    captures thread errors.
    """

    def test_closing_while_serving_raises_nothing_in_the_thread(self):
        errors: list[BaseException] = []
        hook = threading.excepthook
        threading.excepthook = lambda args: errors.append(args.exc_value)
        try:
            loop = _auth_flow.start_loopback()
            loop._server.server_close()
            loop._thread.join(timeout=5)
            assert not loop._thread.is_alive(), "the serve loop did not stop"
        finally:
            threading.excepthook = hook
        assert errors == [], f"the serve thread raised on shutdown: {errors}"

    def test_closing_after_a_real_redirect_is_also_quiet(self):
        errors: list[BaseException] = []
        hook = threading.excepthook
        threading.excepthook = lambda args: errors.append(args.exc_value)
        try:
            loop = _auth_flow.start_loopback()
            urllib.request.urlopen(
                f"http://127.0.0.1:{loop.port}/?code=abc&state=xyz", timeout=3).read()
            loop._collector.arrived.wait(3)
            loop._thread.join(timeout=5)
            loop._server.server_close()
        finally:
            threading.excepthook = hook
        assert errors == []

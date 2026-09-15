"""The `login` subcommand — the only code path permitted to run interactive consent.

Isolated in its own module on purpose. The server imports `_config`, never this, so
`InstalledAppFlow` is not reachable from the stdio process even by mistake: it is not in
the call graph. `run_local_server()` prints the consent URL with a bare `print()` and
blocks on the browser redirect — harmless in a terminal, fatal under stdio where stdout
carries JSON-RPC.
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
from collections.abc import Mapping

from ..auth import load_cached_credentials, read_client_secrets, token_path_for
from ..exceptions import AuthError
from ..workspace import Workspace
from ._config import Settings

# Where the CSA setup scripts place the OAuth client. `login` falls back to this when
# CSA_GW_CLIENT_SECRETS is unset, because requiring an env var that points at a path this
# package itself chose only makes the user rediscover our own convention — which is
# exactly what happened the first time someone ran it.
DEFAULT_CLIENT_SECRETS_PATH = "~/.csa_google_workspace/client_secret.json"   # nosec B105 - a path


@contextlib.contextmanager
def _branded_success_page():
    """Serve the CSA-branded page instead of google_auth_oauthlib's plain-text one.

    `_RedirectWSGIApp.__call__` hardcodes `Content-type: text/plain`, so the public
    `success_message=` argument cannot carry markup — it would render as visible tags.
    Swapping the class for the duration of the flow is the only seam.

    Scope is deliberately narrow: the replacement changes the *response body only* and
    still records `last_request_uri`, which is the security-relevant part (it carries the
    authorization code, and oauthlib validates `state` from it). Token exchange is
    untouched.

    Every failure path falls back to the stock page. A cosmetic upgrade must never be able
    to break authorization — if the private class is renamed or reshaped upstream, login
    keeps working and just looks plainer.
    """
    try:
        import wsgiref.util

        import google_auth_oauthlib.flow as _flow
        original = _flow._RedirectWSGIApp
    except (ImportError, AttributeError):
        yield
        return

    from ._success_page import SUCCESS_HTML

    class _BrandedRedirectApp:
        def __init__(self, success_message):
            self.last_request_uri = None
            self._success_message = success_message      # kept for signature compatibility

        def __call__(self, environ, start_response):
            start_response("200 OK", [("Content-type", "text/html; charset=utf-8")])
            self.last_request_uri = wsgiref.util.request_uri(environ)
            return [SUCCESS_HTML.encode("utf-8")]

    _flow._RedirectWSGIApp = _BrandedRedirectApp
    try:
        yield
    finally:
        _flow._RedirectWSGIApp = original


def _client_id_of(path: str) -> str | None:
    """The client_id from a client-secrets file, or None if unreadable.

    None-on-unreadable is deliberate - this only feeds a warning, and a login must not fail
    because the warning could not be computed. But the definition of "unreadable" was too wide:
    this caught `ValueError`, `JSONDecodeError` subclasses it, and a UTF-8 BOM therefore
    disabled the different-OAuth-client warning silently rather than failing anything (#449).
    Reading through `read_client_secrets` narrows it to files that really are unusable.
    """
    try:
        d = read_client_secrets(path)
    except AuthError:
        return None
    return (d.get("installed") or d.get("web") or {}).get("client_id") or None


def _token_client_id(token_path: str) -> str | None:
    # `utf-8` explicitly: its sibling `_client_id_of` was fixed in #449 and this was missed.
    # A token is ASCII JSON today, so this is the "correct, lucky, or broken" case rather than a
    # live bug - but the locale default is a property of the AUTHOR'S machine, never of the file.
    try:
        with open(os.path.expanduser(token_path), encoding="utf-8") as f:
            return json.load(f).get("client_id") or None
    except (OSError, ValueError):
        return None


def login(settings: Settings, env: Mapping[str, str], *, force: bool = False, out=None) -> int:
    """Run interactive OAuth and cache the token. Returns a process exit code."""
    out = out or sys.stdout
    client_secrets = env.get("CSA_GW_CLIENT_SECRETS")
    if not client_secrets:
        default = os.path.expanduser(DEFAULT_CLIENT_SECRETS_PATH)
        if os.path.exists(default):
            client_secrets = default
        else:
            print("No OAuth client secrets found. Looked at:\n"
                  "  $CSA_GW_CLIENT_SECRETS  (not set)\n"
                  f"  {DEFAULT_CLIENT_SECRETS_PATH}  (does not exist)\n"
                  "Set CSA_GW_CLIENT_SECRETS to your Desktop-app OAuth client JSON, or put it "
                  "at the path above.", file=sys.stderr)
            return 2

    if not force:
        try:
            load_cached_credentials(settings.token_path, settings.read_only)
        except AuthError:
            pass                                  # nothing usable cached — consent below
        else:
            # A cached token can be valid, carry exactly the right scopes, and still have
            # been issued by a *different* OAuth client. Everything then works while
            # running against the wrong project's quota and consent screen — silently.
            # Worth naming, because no error will ever surface it.
            cache = token_path_for(settings.token_path, settings.read_only)
            want, have = _client_id_of(client_secrets), _token_client_id(cache)
            if want and have and want != have:
                print(f"Warning: the cached token was issued by a different OAuth client\n"
                      f"  cached: {have}\n  wanted: {want}\n"
                      f"Re-authorize with `csa-google-workspace-mcp login --force` to use the "
                      f"intended client.", file=sys.stderr)
            print(f"Already authorized (token cache: {cache}).\n"
                  f"Use `login --force` to authorize again.", file=out)
            return 0

    print(f"Opening a browser to authorize access to your Google Workspace files.\n"
          f"  token cache: {token_path_for(settings.token_path, settings.read_only)}", file=out)
    # force=True bypasses the cache but deletes nothing: the old token is replaced only
    # once a new one exists, so a cancelled consent leaves the previous one working.
    with _branded_success_page():
        Workspace.from_oauth(client_secrets, settings.token_path,
                             read_only=settings.read_only, force=force)
    print("Authorized. The MCP server can now start without prompting.", file=out)
    return 0

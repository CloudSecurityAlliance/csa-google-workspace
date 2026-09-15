"""Loopback OAuth pieces for in-band authorization, without `run_local_server()`.

`InstalledAppFlow.run_local_server()` cannot be used here for two reasons: it `print()`s
the consent URL to stdout (which is the JSON-RPC channel), and it blocks the calling
thread until the browser redirect arrives. In-band auth needs the URL as a *value* to
hand to the client, and needs the wait to happen without stalling the event loop.

So the flow is driven directly:

    start_loopback()            -> a listener on 127.0.0.1:<random port>
    authorization_url(flow)     -> the URL to show the user
    wait_for_redirect(listener) -> the full redirect URI, once Google calls back
    flow.fetch_token(authorization_response=...)

`fetch_token` is given the whole redirect URI rather than a bare code, so oauthlib
validates the `state` parameter for us — that check is what stops a CSRF-style injected
authorization code, and losing it would be the easy mistake in hand-rolling this.

Loopback with a random port is Google's documented pattern for desktop clients ("start an
HTTP listener on a random available port"), and no redirect URI needs pre-registering.
The out-of-band copy/paste alternative no longer exists — Google removed it — so a
listener is not optional.
"""
from __future__ import annotations

import threading
import urllib.parse
import wsgiref.simple_server
import wsgiref.util
from dataclasses import dataclass, field

from ..auth import _write_token, read_client_secrets, scopes_for
from ._success_page import SUCCESS_HTML


class _Collector:
    """WSGI app that records the redirect URI and shows the branded success page."""

    def __init__(self) -> None:
        self.redirect_uri: str | None = None
        self.arrived = threading.Event()

    def __call__(self, environ, start_response):
        uri = wsgiref.util.request_uri(environ)
        query = urllib.parse.parse_qs(environ.get("QUERY_STRING", ""))

        # ONLY AN OAUTH REDIRECT ENDS THE WAIT. This used to accept any path and any method,
        # so the first request to arrive won - and the listener sits on 127.0.0.1 for 300
        # seconds while a browser is open. A favicon fetch, a local port scanner, or any page
        # issuing a cross-origin GET consumed it, and the real redirect was then refused.
        # A stray /favicon.ico does it by accident. (#191/T30)
        #
        # `state` is the discriminator because Google always sends it back, on success and on
        # cancel alike, and nothing else hitting a random high port will carry it. This is not
        # a security check - `state` and PKCE are validated later by oauthlib, during the token
        # exchange - it is a "was this meant for me" check, and the defect was availability.
        #
        # `error` counts as an answer: the user clicking Cancel sends
        # ?error=access_denied&state=..., and treating that as noise would hang the login for
        # the full timeout with nothing on screen explaining why.
        wanted = "state" in query and ("code" in query or "error" in query)
        if not wanted:
            # Answered, not dropped: a hanging scanner is one still holding a connection to a
            # listener that is waiting for a credential.
            start_response("204 No Content", [("Content-Length", "0")])
            return [b""]

        start_response("200 OK", [("Content-type", "text/html; charset=utf-8")])
        self.redirect_uri = uri
        self.arrived.set()
        return [SUCCESS_HTML.encode("utf-8")]


@dataclass
class Loopback:
    """A one-shot local listener for the OAuth redirect."""

    port: int
    _server: wsgiref.simple_server.WSGIServer
    _collector: _Collector
    _thread: threading.Thread = field(repr=False)

    @property
    def redirect_uri_base(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def wait(self, timeout: float) -> str | None:
        """Block until the redirect arrives, or `timeout` seconds pass."""
        self._collector.arrived.wait(timeout)
        return self._collector.redirect_uri

    def close(self) -> None:
        try:
            self._server.server_close()
        except OSError:
            pass


def start_loopback() -> Loopback:
    """Bind 127.0.0.1 on a free port and serve until the OAuth redirect arrives, off-thread.

    Serving in a LOOP rather than exactly once, because one-shot handling meant the first
    request to arrive won whether or not it was the redirect (#191/T30). The loop ends when the
    collector has its answer; the caller closes the server, and the thread is a daemon so a
    process exiting mid-consent is not held open by it.
    """
    collector = _Collector()
    # allow_reuse_address off: fail fast rather than silently share a port.
    wsgiref.simple_server.WSGIServer.allow_reuse_address = False
    server = wsgiref.simple_server.make_server("127.0.0.1", 0, collector,
                                               handler_class=_QuietHandler)
    server.timeout = 0.5          # so the loop notices `arrived` even with no traffic

    def serve_until_answered() -> None:
        while not collector.arrived.is_set():
            try:
                server.handle_request()
            except (OSError, ValueError):
                # The caller closed the socket while this thread was between iterations.
                # BOTH are needed and the second is not obvious: `server_close()` sets the
                # descriptor to -1, and `handle_request()` then fails inside `selectors` with
                # `ValueError: Invalid file descriptor: -1` rather than an OSError. Catching
                # only OSError left an unhandled exception in a daemon thread on every login -
                # invisible in normal use, and noise in any log that captures thread errors.
                #
                # The race is inherent to closing from another thread, so the exception IS the
                # stop signal rather than a failure to handle one.
                return

    thread = threading.Thread(target=serve_until_answered, daemon=True)
    thread.start()
    return Loopback(port=server.server_port, _server=server,
                    _collector=collector, _thread=thread)


class _QuietHandler(wsgiref.simple_server.WSGIRequestHandler):
    """wsgiref logs each request to stderr by default; silence it.

    stderr is safe under stdio (only stdout carries JSON-RPC), but a bare access-log line
    in the middle of an MCP session is noise the user cannot act on.
    """

    def log_message(self, format, *args):  # noqa: A002 - signature fixed by the stdlib
        pass


def build_flow(client_secrets: str, read_only: bool, redirect_uri: str):
    """A google_auth_oauthlib Flow pointed at our loopback, with our scopes."""
    from google_auth_oauthlib.flow import Flow

    # autogenerate_code_verifier EXPLICITLY. It is already the library default, so this
    # changes no behaviour today - it changes what we are relying on. PKCE S256 is a property
    # this flow depends on, and depending on somebody else's default means a future release
    # could turn it off silently. (#191/T28)
    #
    # Note the audit's stated reason for this did NOT hold: it proposed raising the
    # google-auth-oauthlib floor because ">=1.0 admits releases where the default is off", and
    # 1.0.0 already defaults it on. A version bound would constrain what may be INSTALLED; this
    # constrains what the code DOES, which is the thing worth constraining.
    # `from_client_config`, not `from_client_secrets_file`: we read the file ourselves so a
    # UTF-8 BOM does not make a valid client unreadable and a malformed one names itself (#449).
    flow = Flow.from_client_config(read_client_secrets(client_secrets),
                                   scopes=scopes_for(read_only),
                                   autogenerate_code_verifier=True)
    flow.redirect_uri = redirect_uri
    return flow


def consent_url(flow) -> str:
    """The URL to send the user to. `prompt='consent'` so re-auth actually re-prompts."""
    url, _state = flow.authorization_url(access_type="offline", prompt="consent")
    return url


def finish(flow, redirect_uri: str, token_path: str) -> None:
    """Exchange the redirect for a token and persist it with the usual hardening.

    Passing the full `authorization_response` (not a bare code) is deliberate: oauthlib
    validates the `state` parameter from it.
    """
    flow.fetch_token(authorization_response=redirect_uri)
    _write_token(token_path, flow.credentials)

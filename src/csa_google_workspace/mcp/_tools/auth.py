"""The identity tools: `authenticate`, `auth_status` and `whoami`.

Together they answer the three questions a person actually asks of a server that holds a Google
credential, and they are deliberately three tools rather than one: *can I get in* (`authenticate`),
*am I in, and does it still work* (`auth_status`, one bounded check), and *as whom* (`whoami`, one narrow
Drive read). Before #481 this server answered only the first, and identity had to be INFERRED by
calling `list_recent_files` and looking for `"me": true` in `owners` - which costs a real Drive
call, and still cannot tell "not logged in" apart from "logged in but revoked".
"""
from __future__ import annotations

import os
import threading
import uuid
from typing import TYPE_CHECKING

import anyio
from mcp.server import MCPServer
from mcp.server.elicitation import AcceptedUrlElicitation
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from ... import auth as _auth
from ... import exceptions as exc
from ...auth import ScopesMissingError, load_cached_credentials, token_path_for
from .._auth_flow import build_flow, consent_url, finish, start_loopback
from .._config import Settings
from .._schemas import AuthOut, AuthStatusOut, WhoamiOut
from ._base import READ, WRITE

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..server import WorkspaceProviderT


# Seconds to wait for Google before giving up and reporting `cached`. Short on purpose:
# `auth_status` is the tool somebody calls WHEN THINGS ARE ALREADY FAILING, so it must answer
# quickly even when the network is the thing that is broken.
_VERIFY_TIMEOUT = 5.0


def _verify_live(verify, timeout: float | None = None) -> tuple[str, str]:
    """Ask Google whether the cached credential actually works.

    Returns `(outcome, detail)` where outcome is:

      `ok`         - Google answered; detail is the account email, or "" if Drive named none.
      `rejected`   - Google refused the credential; detail is why.
      `unverified` - the question could not be asked; detail says what stopped it.

    Bounded on a THREAD rather than with `signal.alarm`, which is POSIX-only - most of this
    server's users run Windows. A thread that outlives the timeout is left running as a daemon:
    the call is a read-only `about.get`, so the cost of abandoning it is one wasted request, and
    there is no portable way to kill it. Saying so beats pretending otherwise.

    UNCERTAINTY DEGRADES TO `unverified`, never to `rejected`. Only our own typed auth and
    access errors mean "Google refused"; a socket error, a 500 or an SSL failure must not be
    reported as a dead credential, because telling somebody to log in again when their network
    is down is the same kind of wrong answer this verification exists to remove.
    """
    # Read at CALL time, not as a default argument. `timeout=_VERIFY_TIMEOUT` in the signature
    # binds the value once when the module is imported, so the module attribute stops being the
    # knob it looks like - patching it has no effect and the bound cannot be tuned without
    # editing the signature. Found by a test that asserted ELAPSED TIME rather than just the
    # status: the status was already correct, so a status-only assertion would have passed with
    # a five-second wait hidden inside it.
    timeout = _VERIFY_TIMEOUT if timeout is None else timeout
    box: dict[str, object] = {}

    def run() -> None:
        try:
            box["ok"] = verify()
        except BaseException as e:  # noqa: BLE001 - classifying the failure IS the job here
            box["err"] = e

    worker = threading.Thread(target=run, daemon=True, name="auth_status-verify")
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        return "unverified", (f"Google did not answer within {timeout:g}s, so the credential "
                              f"has not been checked upstream.")
    if "err" in box:
        e = box["err"]
        if isinstance(e, (exc.AuthError, exc.AccessError)):
            return "rejected", str(e)
        return "unverified", f"{type(e).__name__}: {e}"
    who = box.get("ok") or {}
    email = (who.get("email_address") if isinstance(who, dict) else None) or ""
    return "ok", email


def _auth_status_payload(token_path: str, read_only: bool,
                         client_secrets: str | None,
                         verify=None) -> AuthStatusOut:
    """No network call, ever - that is the whole point of this existing separately from
    `auth.load_cached_credentials`, which refreshes an expired access token over the wire as
    part of returning usable credentials.

    Takes its inputs as arguments rather than reading `Settings` in here, so it stays a pure
    function of them and is testable without monkeypatching process state.

    `token_path_for`, not the raw path: a read-only posture reads a SEPARATE cache (#185), and
    reporting on the file the server would not actually read is the one wrong answer this
    function could give while looking right.

    EXPANDED ONCE, here, exactly as `load_cached_credentials` does it (#490). The default
    token path is `~/.csa_google_workspace/token.json`, and this used to expand it for the
    existence check and then hand `_read_cached` the raw `~` form - which does not expand it,
    finds nothing, and returns None. So every default install with a perfectly good credential
    was told "the credential cached there is not usable. Call `authenticate` to log in again."

    The bug is the shape this tool exists to avoid: `auth_status` predicts what
    `load_cached_credentials` would say without making its network call, so the two disagreeing
    about WHICH FILE they read makes the prediction worthless while it still looks confident.
    """
    path = os.path.expanduser(token_path_for(token_path, read_only))
    project = _auth.client_project_id(client_secrets)
    # FIRST, because a retired client invalidates everything below it. A credential belonging to
    # a project this repo has migrated away from stops refreshing once Google deletes or
    # unpublishes that project, and the failure arrives as "could not refresh cached
    # credentials" while this function - which then made no network call at all - reported
    # `ready` (#510). That gap is closed below: `ready` is now verified rather than predicted.
    # This branch stays because it is still the better answer for a KNOWN-retired project - it
    # names the cause and the remedy without waiting on a call that will fail.
    #
    # Measured by contrast: an install on csa-drive-docs-mcp refreshes and
    # answers `whoami`; the reporting install was on cino-workspace-mcp and every call failed.
    #
    # Reported ahead of the token checks because `authenticate` against a retired client fails
    # the same way, so "no credential, log in again" would send somebody round the loop that
    # just failed. The client has to be replaced first.
    if project in _auth.RETIRED_CLIENT_PROJECTS:
        return {"status": "client_retired", "token_path": path, "client_project": project,
                "detail": f"The client secrets in use belong to {project}, an OAuth client this "
                          f"project has migrated away from. Credentials issued by it stop "
                          f"refreshing once Google retires the project, which surfaces as "
                          f"'could not refresh cached credentials' on every call - logging in "
                          f"again will not fix it. Re-run the CSA setup script to fetch the "
                          f"current client secrets, then call `authenticate`."}
    if not os.path.exists(path):
        return {"status": "no_credential", "token_path": path, "client_project": project,
                "detail": f"No credential cached at {path}. Call `authenticate` to log in."}
    try:
        # `_read_cached`, not `load_cached_credentials`: the public function refreshes an
        # expired access token over the network before returning, which is exactly the call
        # this function exists to avoid making.
        creds = _auth._read_cached(path, _auth.scopes_for(read_only), read_only=read_only,
                                   explain_missing_scopes=True)
    except ScopesMissingError as e:
        return {"status": "scope_short", "token_path": path, "client_project": project,
                "detail": str(e)}
    except exc.AuthError as e:
        return {"status": "no_credential", "token_path": path, "client_project": project,
                "detail": f"The cached credential at {path} could not be read ({e}). "
                          f"Call `authenticate` to log in again."}
    # `_read_cached` RETURNS None as well as raising - a file that exists but holds nothing
    # usable takes that path. Reporting `ready` for it would be the one answer this function
    # must never give, since every caller reads `ready` as "go ahead and write".
    if creds is None:
        return {"status": "no_credential", "token_path": path, "client_project": project,
                "detail": f"The credential cached at {path} is not usable. "
                          f"Call `authenticate` to log in again."}
    # Everything above is a LOCAL verdict and the states are honest about it. This last one
    # was not: `ready` is a claim that calls will work, and a file read cannot support it.
    # #510 is the bill for that - a token whose OAuth project had been deleted read as `ready`
    # while every call failed. `client_retired` catches that for a hardcoded set of projects
    # and cannot catch a token revoked at myaccount.google.com, scopes revoked at the IdP, a
    # suspended account, or a policy change. So ask.
    if verify is None:
        return {"status": "cached", "token_path": path, "client_project": project,
                "detail": f"Credential cached at {path} with every required scope. NOT checked "
                          f"against Google - no verifier was available, so this says the file "
                          f"is well formed and nothing more."}
    outcome, why = _verify_live(verify)
    if outcome == "rejected":
        return {"status": "credential_rejected", "token_path": path, "client_project": project,
                "detail": f"Google refused the credential cached at {path}: {why} Logging in "
                          f"again is the usual fix; if it fails the same way, the OAuth client "
                          f"itself is the problem rather than the token."}
    if outcome == "unverified":
        return {"status": "cached", "token_path": path, "client_project": project,
                "detail": f"Credential cached at {path} with every required scope, but it could "
                          f"not be checked against Google: {why} The file is well formed; "
                          f"whether Google still accepts it is unknown."}
    return {"status": "ready", "token_path": path, "client_project": project,
            "detail": (f"Verified against Google{f' as {why}' if why else ''}. "
                       f"Credential cached at {path} with every required scope.")}


def register_auth_tools(app: MCPServer, settings: Settings,
                        get_workspace: WorkspaceProviderT) -> None:
    """The `authenticate` tool: browser consent driven from inside the MCP client.

    MCP's own OAuth is for HTTP transports and authenticates the *client to the server*; we
    need the opposite — this server authorizing outbound to Google. For stdio the spec says
    to take credentials from the environment, which is what `login` does. **URL-mode
    elicitation** (added in revision `2026-07-28`) is the sanctioned way to do it in-band:
    the server hands the client a URL to send the user to, and the sensitive exchange
    happens out-of-band, never through the model's context.

    Falls back cleanly. A client without URL elicitation — Claude Desktop today — gets a
    plain instruction to run `login` in a terminal, which is exactly the behaviour before
    this tool existed. And because both clients share one token file, a user who
    authenticates here in Claude Code has also authenticated Claude Desktop.
    """

    @app.tool(annotations=WRITE)
    async def authenticate(ctx: Context, force: bool = False) -> AuthOut:
        """Authorize this server to reach your Google Drive, via your browser.

        Call this when another tool reports missing credentials. Use force=True to
        re-authorize (for example if the cached token belongs to the wrong account)."""
        if not force:
            try:
                await anyio.to_thread.run_sync(
                    lambda: load_cached_credentials(settings.token_path, settings.read_only))
            except exc.AuthError:
                pass
            else:
                return {"status": "already_authorized",
                        "detail": f"A usable token is already cached at "
                                  f"{token_path_for(settings.token_path, settings.read_only)}. "
                                  f"Pass force=true to authorize again."}

        if not settings.client_secrets:
            raise ToolError(
                "No OAuth client is configured, so a consent URL cannot be built. Set "
                "CSA_GW_CLIENT_SECRETS or place the client at "
                "~/.csa_google_workspace/client_secret.json, then run "
                "`csa-google-workspace-mcp login` in a terminal.")

        loopback = start_loopback()
        try:
            flow = build_flow(settings.client_secrets, settings.read_only,
                              loopback.redirect_uri_base)
            url = consent_url(flow)
            elicitation_id = uuid.uuid4().hex

            try:
                answer = await ctx.elicit_url(
                    message=("Authorize access to your Google Docs, Sheets and Slides. "
                             "You will sign in as yourself and reach only your own files."),
                    url=url,
                    elicitation_id=elicitation_id,
                )
            except Exception as e:
                # No URL elicitation support (or the client refused the request). Degrade to
                # the terminal path rather than failing outright.
                raise ToolError(
                    "This client cannot open an authorization URL for me. Run "
                    "`csa-google-workspace-mcp login` in a terminal instead — it does the "
                    "same thing, once.") from e

            if not isinstance(answer, AcceptedUrlElicitation):
                return {"status": "declined",
                        "detail": "Authorization was not started. Nothing changed."}

            # Wait off-thread: the listener blocks, and the event loop must not.
            redirect = await anyio.to_thread.run_sync(lambda: loopback.wait(300.0))
            if not redirect:
                return {"status": "timed_out",
                        "detail": "No response from the browser within 5 minutes. "
                                  "Call authenticate again when ready."}

            await anyio.to_thread.run_sync(
                # token_path_for, not settings.token_path: a read-only posture reads a
                # separate cache (#185), and writing the token where nothing reads it
                # would make CSA_GW_READ_ONLY=1 impossible to satisfy.
                lambda: finish(flow, redirect,
                               token_path_for(settings.token_path, settings.read_only)))
            await ctx.session.send_elicit_complete(elicitation_id)
            return {"status": "authorized",
                    "detail": f"Token cached at "
                        f"{token_path_for(settings.token_path, settings.read_only)}. "
                        f"Both Claude Code and "
                              f"Claude Desktop use this file, so neither needs authorizing again."}
        finally:
            loopback.close()

    @app.tool(annotations=READ)
    def auth_status() -> AuthStatusOut:
        """Whether a credential is cached, whether it covers every scope this deployment needs,
        and - if so - whether Google still accepts it. Makes ONE bounded call and never returns
        the credential itself.

        Call this BEFORE `authenticate` rather than guessing from a failed tool call. Three
        states, not two: `no_credential` (nothing usable cached - call `authenticate`),
        `scope_short` (a credential IS cached and IS valid, it just predates a scope this
        deployment has since started requiring - also `authenticate`, but the fix is a
        re-consent, not a first login), and `ready`.

        Every state also carries `client_project`: the Google Cloud project this deployment's
        OAuth client belongs to, or `None` if none is configured or it could not be read. That
        is the answer a consent flow never gave - which project a call is about to run against -
        and it is how a person tells which side of the `cino-workspace-mcp` -> `csa-drive-docs-mcp`
        migration a token is on."""
        return _auth_status_payload(settings.token_path, settings.read_only,
                                    settings.client_secrets,
                                    verify=lambda: get_workspace().whoami())

    @app.tool(annotations=READ)
    def whoami() -> WhoamiOut:
        """Which Google account this server is signed in as - the email address and display
        name, and nothing else.

        One narrow `about.get`; it reads no files. Before this existed the only way to establish
        identity was to call `list_recent_files` and infer it from `"me": true` in `owners`,
        which costs a real Drive call and cannot distinguish "not logged in" from "logged in but
        revoked" - use `auth_status` for that question, which distinguishes all five states
        and verifies against Google rather than predicting.

        Worth checking before a write. This server can hold read AND modify scope over every
        file the credential can reach, including sharing and trashing, so a token belonging to
        the wrong account should be caught before it acts rather than after - that is the case
        `authenticate(force=True)` exists for."""
        # Built key by key rather than returned straight through: `Workspace.whoami` is a
        # library method with a library return type, and the wire shape is a contract this
        # module owns. Widening one to match the other would couple them in the wrong
        # direction.
        who = get_workspace().whoami()
        return {"email_address": who["email_address"],
                "display_name": who["display_name"]}

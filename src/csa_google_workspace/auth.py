"""OAuth installed-app flow + scope logic. Acts as a real user; writes on by default."""
import json
import os

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .exceptions import AuthError

_BASE = "https://www.googleapis.com/auth/"
_RW = [f"{_BASE}drive", f"{_BASE}documents", f"{_BASE}spreadsheets", f"{_BASE}presentations"]
_RO = [f"{s}.readonly" for s in _RW]

# Drive **labels**, and read-only in BOTH postures - the only scope here that does not have a
# write form, deliberately.
#
# Labels are a classification system: DLP and retention key on them, so writing one is not an
# edit to a document, it is a claim about how the organisation must treat that document. A model
# that could relabel `Confidential` to `Public` would be defeating a control rather than using
# one. Reading them is the useful half anyway - "what is this document classified as?" is the
# question people actually ask - so this library asks for `.readonly` and cannot mislabel
# anything even when the operator has enabled every capability.
#
# It is also a SEPARATE API (`drivelabels.googleapis.com`). A granted scope does not enable an
# API: until it is switched on in the Cloud project these calls 403 `SERVICE_DISABLED`, which is
# why `labels.py` degrades to ids-without-names rather than failing the call.
_LABELS_RO = f"{_BASE}drive.labels.readonly"


def scopes_for(read_only: bool) -> list[str]:
    """The scopes to request. `_LABELS_RO` is in both postures because it has no write form."""
    return [*(_RO if read_only else _RW), _LABELS_RO]


def token_path_for(token_path: str, read_only: bool) -> str:
    """The cache file a posture uses. Read-only gets its own, derived from the configured path.

    A read-write token genuinely satisfies a read-only scope set at Google, so sharing one cache
    made `CSA_GW_READ_ONLY=1` a client-side `Policy` over a full-write credential rather than a
    narrower credential. Separating the files means the guarantee is *which file exists* (#185).

    Derived rather than configured on purpose: an operator asked to set two paths will set one,
    and the one they forget is the one that silently falls back to the wrong posture.
    """
    if not read_only:
        return token_path
    base, ext = os.path.splitext(token_path)
    if base.endswith(".readonly"):
        return token_path          # idempotent: an operator may configure the derived path
    return f"{base}.readonly{ext or '.json'}"


def has_write_scope(granted: list[str]) -> bool:
    """Does this credential carry any scope that can change something?

    **A SUBSET CHECK, not an allowlist of known write scopes (#327).** The previous version
    asked *"does the token carry one of OUR four write scopes?"*, which is a denylist wearing
    different clothes — and a denylist can be walked around by anything not on it. A token
    carrying `drive.file`, a real write scope this project happens never to request, answered
    **False** and passed as read-only.

    That mattered because of where it is used: deciding whether a cached credential is safe for
    a read-only posture (`:130`). A token that can write, accepted as one that cannot, is the
    exact failure `CSA_GW_READ_ONLY=1` exists to prevent.

    So the question is inverted. Anything **outside** the read-only set is treated as a write
    scope, whether or not this project has heard of it. An unlisted scope can no longer outflank
    the check, and a scope Google adds tomorrow is handled correctly the day it appears.

    A credential with **no** scopes reported is not a licence: `granted` is empty on some
    refresh paths, and answering "no write scopes" there would be the permissive reading of
    missing information. It answers `True` — the conservative direction, matching the rule this
    codebase follows everywhere that absence and denial look alike.
    """
    scopes = set(granted or [])
    if not scopes:
        return True
    return not scopes <= set(scopes_for(read_only=True))


def needs_reconsent(granted: list[str], required: list[str]) -> bool:
    granted_set = set(granted or [])
    for scope in required:
        if scope in granted_set:
            continue
        base = scope[: -len(".readonly")] if scope.endswith(".readonly") else None
        if base and base in granted_set:
            continue  # a granted RW scope satisfies a required readonly scope
        return True
    return False


class ScopesMissingError(AuthError):
    """A cached token exists and is loadable, but is short of scopes.

    Its own type, not a message, because the CALLER needs to word things differently: "your
    login is fine but one scope short" is a different instruction from "you have not logged in",
    and the fix is the same command while the explanation is not. `scopes` is the difference,
    shortened to leaf names for reading - the full URLs are noise in a terminal.
    """

    def __init__(self, missing: list[str]) -> None:
        self.scopes = list(missing)
        leaves = ", ".join(s.rsplit("/", 1)[-1] for s in self.scopes)
        super().__init__(
            f"cached credentials lack {len(self.scopes)} required scope(s): {leaves}. The token "
            f"itself is present and valid - it was issued before this version needed that "
            f"scope - so this is a re-consent, not a lost login.")


def _read_cached(token_path: str, required: list[str], *,
                 read_only: bool = False,
                 explain_missing_scopes: bool = False) -> Credentials | None:
    """The token cache, or None if absent / scope-stale — both meaning 'consent is needed'.

    `explain_missing_scopes` picks which of two callers is asking, and they genuinely want
    opposite things:

    * the **interactive** path (`load_credentials`) treats a scope-short token as "go and get
      consent" and falls through to the browser flow, so it wants a bare `None`. Raising here
      broke that fallback, which is why this is a flag rather than a change of behaviour;
    * the **non-interactive** path (`load_cached_credentials`, the stdio MCP server) cannot
      prompt, so `None` becomes a message a human reads — and it must say the token is present
      and one scope short rather than absent.
    """
    if not os.path.exists(token_path):
        return None
    try:
        creds = Credentials.from_authorized_user_file(token_path)
    except (ValueError, GoogleAuthError) as e:
        # Generic message: don't interpolate the cause (may echo token material). The
        # original is preserved via `from e` for debugging (#19).
        raise AuthError("could not load cached credentials") from e
    granted = list(creds.scopes or [])
    # A READ-ONLY POSTURE REFUSES A WRITE CREDENTIAL. `needs_reconsent` would accept one -
    # correctly, as a statement about OAuth scopes - and accepting its answer here was the
    # defect (#185): it made CSA_GW_READ_ONLY=1 a client-side Policy over a full-Drive token,
    # so any path reaching the credential without passing the Policy gates had full write. Both
    # prior audits name a read-only posture as the primary bound on prompt injection, which made
    # the top risk's main mitigation fail open.
    #
    # `token_path_for` already separates the caches, and this is the second half rather than a
    # duplicate: file separation alone is a FILENAME guarantee, and a token copied to the
    # read-only path, or a broad grant at the consent screen, reopens the hole.
    #
    # The old comment cited headless refresh as the reason for sharing the cache. That reason
    # survives: each file refreshes on its own, with no browser.
    if read_only and has_write_scope(granted):
        raise AuthError(
            "this token carries WRITE scopes and the server is configured read-only, so it "
            "will not be used - a read-only posture has to mean a read-only credential, not a "
            "full-Drive one with writes blocked in software. Run the login again with "
            "CSA_GW_READ_ONLY=1 set to consent to read-only scopes; it is written to a separate "
            "cache file, so the read-write token you already have is left untouched.")
    missing = [s for s in required if s not in set(granted)]
    if missing and explain_missing_scopes:
        # NAME THE MISSING SCOPES. Returning a bare None here was the whole of the defect: a
        # token that is present, valid, and one scope short is indistinguishable from no token
        # at all, and the caller's message then said "no usable token" about a file sitting
        # right there. v0.34.0 is the first release that can produce this state - adding
        # `drive.labels.readonly` made every existing working token insufficient - and every
        # future scope addition does it again.
        raise ScopesMissingError(missing)
    if missing:
        return None                     # interactive caller: fall through to consent
    return creds


def _refresh(creds: Credentials) -> None:
    try:
        creds.refresh(Request())
    except (ValueError, GoogleAuthError) as e:
        raise AuthError("could not refresh cached credentials") from e


def _write_token(token_path: str, creds: Credentials) -> None:
    token_dir = os.path.dirname(token_path)
    if token_dir and not os.path.isdir(token_dir):
        os.makedirs(token_dir, exist_ok=True)
        os.chmod(token_dir, 0o700)      # only harden a dir we created; don't mutate a caller's (#4)
    # O_NOFOLLOW refuses a symlink at token_path (symlink/TOCTOU attack); fchmod enforces
    # 0o600 even when the file already existed, since O_TRUNC keeps a file's prior mode (#17).
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w") as f:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        f.write(creds.to_json())


# Where a client-secrets file comes from, said once. Every failure below ends with this,
# because "your file is wrong" without "and here is the file you should have" is half an error.
_WHERE_FROM = ("It must be the JSON for a Google Cloud OAuth client of type **Desktop app**. "
               "Download it from the Cloud console, or install the CSA one, then point "
               "CSA_GW_CLIENT_SECRETS at it or place it at "
               "~/.csa_google_workspace/client_secret.json.")


def read_client_secrets(path: str) -> dict:
    """Parse an OAuth client-secrets file into a client config, or raise an actionable `AuthError`.

    This exists so that **we** open the file rather than `google_auth_oauthlib`, for two reasons
    that are worth keeping apart (#449).

    **Encoding.** `from_client_secrets_file` opens with no `encoding=` argument, so a UTF-8 BOM
    lands at char 0 and `json.load` refuses a file that is perfectly valid JSON. A BOM is legal
    and common on Windows - `Set-Content -Encoding utf8` emits one under Windows PowerShell 5.1
    though not under PowerShell 7 - so tolerating it belongs in the client, not in a rule about
    who may write the file. `utf-8-sig` strips a BOM when present and is a no-op when absent.

    **Actionability.** The upstream failure is `Expecting value: line 1 column 1 (char 0)` raised
    from inside a dependency, naming neither the path nor the fact that a client-secrets file was
    being read. That is unactionable even when the file genuinely IS malformed, which is the case
    that outlives the BOM. Every raise here names the path, says what the file is for, and keeps
    the underlying parse detail rather than swallowing it.

    Callers hand the result to `from_client_config`. All three readers in the tree go through
    here, including `_login._client_id_of`, whose `except ValueError` silently caught the
    `JSONDecodeError` (it subclasses `ValueError`) and disabled the wrong-OAuth-client warning.
    """
    try:
        with open(os.path.expanduser(path), encoding="utf-8-sig") as f:
            config = json.load(f)
    except FileNotFoundError:
        raise AuthError(f"No OAuth client secrets at {path}. {_WHERE_FROM}") from None
    except OSError as e:
        raise AuthError(f"Could not read the OAuth client secrets at {path}: {e}") from None
    except json.JSONDecodeError as e:
        # `e` carries "line 1 column 1 (char 0)"; keep it - it is the only thing that
        # distinguishes a BOM-like problem at char 0 from a truncated file at char 4000.
        raise AuthError(f"The OAuth client secrets at {path} are not valid JSON: {e}. "
                        f"{_WHERE_FROM}") from None
    if not isinstance(config, dict) or not (config.get("installed") or config.get("web")):
        # Valid JSON, wrong document. Overwhelmingly a service-account key. Upstream's own
        # message ("Client secrets must be for a web or installed app") names no file, and when
        # two candidate files are on disk that is the whole question.
        top = ", ".join(sorted(config)) if isinstance(config, dict) else type(config).__name__
        raise AuthError(f"The JSON at {path} is not an OAuth client: it has no 'installed' or "
                        f"'web' key (found: {top}). {_WHERE_FROM}")
    return config


def load_credentials(client_secrets: str, token_path: str, read_only: bool,
                     *, force: bool = False) -> Credentials:
    """Interactive: reuse the cache, else open a browser for consent. Terminal use only.

    `force=True` ignores the cache and re-consents. It does not delete anything: the
    existing token is replaced only once a new one is in hand, so a cancelled or failed
    consent leaves the old credentials working.

    Do NOT call this from a stdio MCP server — `run_local_server()` prints the consent URL
    to stdout (the JSON-RPC channel) and blocks on the browser redirect. Servers call
    `load_cached_credentials` instead, which has no such branch.
    """
    required = scopes_for(read_only)
    token_path = os.path.expanduser(token_path_for(token_path, read_only))
    creds = None if force else _read_cached(token_path, required, read_only=read_only)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        _refresh(creds)
    else:
        config = read_client_secrets(client_secrets)    # we open it; see read_client_secrets (#449)
        creds = InstalledAppFlow.from_client_config(config, required).run_local_server(port=0)
    _write_token(token_path, creds)
    return creds


def load_cached_credentials(token_path: str, read_only: bool) -> Credentials:
    """Non-interactive: usable credentials from the token cache, or `AuthError`.

    This function deliberately contains **no** `InstalledAppFlow` branch, so a caller that
    must never prompt — the stdio MCP server — cannot reach interactive consent even by
    mistake. That is a structural guarantee rather than a convention. Refreshing an expired
    token is pure HTTP with no stdout writes, so it stays on this path.

    No `client_secrets` argument is needed: `to_json()` persists client_id/client_secret/
    token_uri into the cache, so a cached token is self-sufficient for refresh.
    """
    token_path = os.path.expanduser(token_path_for(token_path, read_only))
    if not os.path.exists(token_path):
        raise AuthError(
            "no cached credentials" + (
                " for a read-only posture. CSA_GW_READ_ONLY=1 uses its own cache file, so a "
                "read-write token elsewhere does not satisfy it - run the login again with "
                "CSA_GW_READ_ONLY=1 set." if read_only else ""))
    # `_read_cached` now raises `ScopesMissingError` (naming the scopes) rather than returning
    # None for a scope-short token, so a None here means only "nothing loadable".
    creds = _read_cached(token_path, scopes_for(read_only), read_only=read_only,
                         explain_missing_scopes=True)
    if creds is None:
        raise AuthError("no usable cached credentials")
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        _refresh(creds)
        _write_token(token_path, creds)     # persist the refreshed token
        return creds
    raise AuthError("cached credentials are invalid and cannot be refreshed")

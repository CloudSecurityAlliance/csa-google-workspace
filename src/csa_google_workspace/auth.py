"""OAuth installed-app flow + scope logic. Acts as a real user; writes on by default."""
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

_BASE = "https://www.googleapis.com/auth/"
_RW = [f"{_BASE}drive", f"{_BASE}documents", f"{_BASE}spreadsheets", f"{_BASE}presentations"]
_RO = [f"{s}.readonly" for s in _RW]


def scopes_for(read_only: bool) -> list[str]:
    return list(_RO if read_only else _RW)


def needs_reconsent(granted: list[str], required: list[str]) -> bool:
    return not set(required).issubset(set(granted or []))


def load_credentials(client_secrets: str, token_path: str, read_only: bool) -> Credentials:
    required = scopes_for(read_only)
    token_path = os.path.expanduser(token_path)
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path)
        if needs_reconsent(list(creds.scopes or []), required):
            creds = None  # cached token lacks the scopes we now need → re-consent
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        creds = InstalledAppFlow.from_client_secrets_file(client_secrets, required).run_local_server(port=0)
    token_dir = os.path.dirname(token_path) or "."
    os.makedirs(token_dir, exist_ok=True)
    os.chmod(token_dir, 0o700)
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(creds.to_json())
    return creds

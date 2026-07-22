"""Entry point. Workspace.open() sniffs MIME type and returns the right typed Document."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .backend import ApiBackend, Backend
from .base import Document, subclass_for_mime

if TYPE_CHECKING:
    from google.auth.credentials import Credentials

_ID_IN_URL = re.compile(r"/d/([a-zA-Z0-9_-]+)")


def parse_file_id(url_or_id: str) -> str:
    """Extract a Drive file id from a share URL, or return the input unchanged if it's already a bare id."""
    m = _ID_IN_URL.search(url_or_id)
    return m.group(1) if m else url_or_id


class Workspace:
    def __init__(self, backend: Backend, read_only: bool = False):
        self._backend = backend
        self.read_only = read_only

    def open(self, file_id_or_url: str) -> Document:
        file_id = parse_file_id(file_id_or_url)
        meta = self._backend.get_file_metadata(file_id)
        cls = subclass_for_mime(meta["mimeType"])
        return cls(self._backend, meta, read_only=self.read_only)

    def open_by_url(self, url: str) -> Document:
        return self.open(url)

    @classmethod
    def from_credentials(cls, credentials: Credentials, read_only: bool = False) -> Workspace:
        """Bring your own credentials: wrap any google.auth Credentials
        (a user's OAuth credentials, or a service account's) into a Workspace."""
        from ._services import ServiceRegistry
        return cls(ApiBackend(ServiceRegistry(credentials)), read_only=read_only)

    @classmethod
    def from_oauth(cls, client_secrets: str,
                   token_path: str = "~/.csa_google_workspace/token.json",  # nosec B107 - default path, not a secret
                   read_only: bool = False) -> Workspace:
        from .auth import load_credentials
        creds = load_credentials(client_secrets, token_path, read_only)
        return cls.from_credentials(creds, read_only=read_only)

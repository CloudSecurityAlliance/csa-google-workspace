"""Entry point. Workspace.open() sniffs MIME type and returns the right typed Document."""
from __future__ import annotations

import re

from .backend import Backend, ApiBackend
from .base import Document, subclass_for_mime

_ID_IN_URL = re.compile(r"/d/([a-zA-Z0-9_-]+)")


def parse_file_id(url_or_id: str) -> str:
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
    def from_oauth(cls, client_secrets: str,
                   token_path: str = "~/.csa_google_workspace/token.json",
                   read_only: bool = False) -> "Workspace":
        from .auth import load_credentials
        from ._services import ServiceRegistry
        creds = load_credentials(client_secrets, token_path, read_only)
        return cls(ApiBackend(ServiceRegistry(creds)), read_only=read_only)

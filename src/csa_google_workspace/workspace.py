"""Entry point. Workspace.open() sniffs MIME type and returns the right typed Document."""
from __future__ import annotations

import re
import warnings
from typing import TYPE_CHECKING

from .backend import ApiBackend, Backend
from .base import Document, subclass_for_mime
from .files import FileCollection
from .policy import Policy, PolicyBackend
from .restrictions import SharedDrive

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

    def whoami(self) -> dict[str, str | None]:
        """The account this workspace is acting as: `email_address` and `display_name`.

        A library method rather than something the MCP tool assembles, so the answer to "who am
        I signed in as" is available to anyone using this package directly - the same seam rule
        every control here follows. The server's `whoami` tool is a one-line wrapper.

        Both values are `None` when Drive returns no `user` node. Unknown is not absent, and a
        caller must be able to tell "Drive did not say" from "the address is empty".
        """
        user = self._backend.get_about_user()
        return {"email_address": user.get("emailAddress") or None,
                "display_name": user.get("displayName") or None}

    @property
    def files(self) -> FileCollection:
        """The account axis: find files, rather than operate on one you already named.

        A property, not a stored attribute, so a `Workspace` stays cheap to construct and
        holds no per-axis state — the same reason `Document.comments` is a property.
        """
        return FileCollection(self._backend, self.read_only)

    def shared_drive(self, drive_id: str) -> SharedDrive:
        """A shared drive and its restrictions (#338) — the broadest Google-side controls.

        These bound an entire drive and every file in it: `drive_members_only`,
        `domain_users_only`, `copy_requires_writer_permission`,
        `sharing_folders_requires_organizer_permission`, and the download restriction.

        **Why reading this matters for a tool that shares files:** a document living in a drive
        with `drive_members_only` cannot be shared outward however our own policy is configured
        — Drive will refuse. Being unable to read that meant the server could not tell a model
        that an action it was about to attempt was already impossible.

        `driveId` comes from `FileRef.drive_id` or `get_file_metadata`; a file **not** in a
        shared drive has none, and passing one for a My Drive file is a question with no answer
        rather than an error to invent. **Read-only by construction** — there is no
        `update_drive` here and no capability to enable one, for the same reason `labels.py`
        cannot write: a control this broad is the last thing an agent should be able to lift.
        """
        return SharedDrive.from_api(self._backend.get_drive(drive_id))

    def open(self, file_id_or_url: str) -> Document:
        file_id = parse_file_id(file_id_or_url)
        meta = self._backend.get_file_metadata(file_id)
        cls = subclass_for_mime(meta["mimeType"])
        return cls(self._backend, meta, read_only=self.read_only)

    def open_by_url(self, url: str) -> Document:
        """Deprecated: `open()` already accepts a URL or a bare file id."""
        warnings.warn("open_by_url() is deprecated; open() accepts URLs and file ids too.",
                      DeprecationWarning, stacklevel=2)
        return self.open(url)

    @classmethod
    def from_credentials(cls, credentials: Credentials, read_only: bool = False, *,
                         policy: Policy | None = None) -> Workspace:
        """Bring your own credentials: wrap any google.auth Credentials
        (a user's OAuth credentials, or a service account's) into a Workspace.

        A capability `policy` is applied by default (`Policy.default()`), which permits
        exactly what this library has always permitted and refuses the operations that
        alter or expose an existing file — rename/move, trash, share. Pass one explicitly to
        widen or narrow it. `read_only=True` overrides everything with an empty policy.

        This constructor is safe by default on purpose. An embedder who genuinely wants an
        ungated backend builds one through the documented seam instead:
        `Workspace(ApiBackend(ServiceRegistry(creds)))`.
        """
        from ._services import ServiceRegistry
        backend = ApiBackend(ServiceRegistry(credentials))
        effective = Policy(enabled=frozenset()) if read_only else (policy or Policy.default())
        return cls(PolicyBackend(backend, effective), read_only=read_only)

    @classmethod
    def from_oauth(cls, client_secrets: str,
                   token_path: str = "~/.csa_google_workspace/token.json",  # nosec B107 - default path, not a secret
                   read_only: bool = False, *, force: bool = False,
                   policy: Policy | None = None) -> Workspace:
        from .auth import load_credentials
        creds = load_credentials(client_secrets, token_path, read_only, force=force)
        return cls.from_credentials(creds, read_only=read_only, policy=policy)

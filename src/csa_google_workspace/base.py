"""Document base + MIME→subclass mapping. Subclasses live in documents/."""
from __future__ import annotations

from .backend import Backend
from . import exceptions as exc
from .comments import CommentCollection, Comment

MIME_TO_TYPE = {
    "application/vnd.google-apps.document": "document",
    "application/vnd.google-apps.spreadsheet": "spreadsheet",
    "application/vnd.google-apps.presentation": "presentation",
}


class CommentsMixin:
    @property
    def comments(self) -> CommentCollection:
        return CommentCollection(self._backend, self.id, self.read_only,
                                 locate=getattr(self, "_locate_comment", None))

    def create_comment(self, content: str) -> Comment:
        if self.read_only:
            raise exc.ReadOnlyError("workspace is read_only; cannot create a comment")
        d = self._backend.create_comment(self.id, content)
        return self.comments._wrap(d)


class Document(CommentsMixin):
    """Abstract base. Never instantiated directly — use Workspace.open()."""

    def __init__(self, backend: Backend, metadata: dict, read_only: bool):
        self._backend = backend
        self.id = metadata["id"]
        self.name = metadata.get("name", "")
        self.mime_type = metadata["mimeType"]
        self.type = MIME_TO_TYPE[self.mime_type]
        self.url = metadata.get("webViewLink", "")
        self.read_only = read_only

    def reload(self) -> None:
        """Drop cached state (none yet in Phase 1)."""

    def export(self, mime_type: str) -> bytes:
        return self._backend.export_file(self.id, mime_type)

    def _require_writable(self) -> None:
        if self.read_only:
            from . import exceptions as exc
            raise exc.ReadOnlyError("workspace is read_only; content writes are disabled")


def subclass_for_mime(mime: str) -> type[Document]:
    if mime not in MIME_TO_TYPE:
        raise exc.UnsupportedOperation(f"unsupported file type: {mime}")
    from .documents.doc import Doc
    from .documents.sheet import Sheet
    from .documents.slides import Slides
    return {"document": Doc, "spreadsheet": Sheet, "presentation": Slides}[MIME_TO_TYPE[mime]]

from ..base import Document
from .. import _content


class Doc(Document):
    """Google Docs. Content read; write + suggestions arrive in later phases."""

    def as_text(self) -> str:
        return _content.doc_text(self._backend.get_document(self.id))

    @property
    def paragraphs(self) -> list[str]:
        return _content.doc_paragraphs(self._backend.get_document(self.id))

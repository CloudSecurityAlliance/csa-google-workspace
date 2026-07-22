from ..base import Document
from .. import _content


class Doc(Document):
    """Google Docs. Content read; write + suggestions arrive in later phases."""

    def as_text(self) -> str:
        return _content.doc_text(self._backend.get_document(self.id))

    @property
    def paragraphs(self) -> list[str]:
        return _content.doc_paragraphs(self._backend.get_document(self.id))

    def replace_text(self, find: str, replace: str) -> None:
        self._require_writable()
        self._backend.docs_batch_update(self.id, [{"replaceAllText": {
            "containsText": {"text": find, "matchCase": True}, "replaceText": replace}}])

    def insert_text(self, text: str, at: int) -> None:
        self._require_writable()
        self._backend.docs_batch_update(self.id, [{"insertText": {"location": {"index": at}, "text": text}}])

    def append_text(self, text: str) -> None:
        self._require_writable()
        content = self._backend.get_document(self.id).get("body", {}).get("content", [])
        end = content[-1].get("endIndex", 2) if content else 2
        self._backend.docs_batch_update(self.id, [{"insertText": {"location": {"index": end - 1}, "text": text}}])

    def delete_range(self, start: int, end: int) -> None:
        self._require_writable()
        self._backend.docs_batch_update(self.id, [{"deleteContentRange": {
            "range": {"startIndex": start, "endIndex": end}}}])

    def batch_update(self, requests: list) -> dict:
        self._require_writable()
        return self._backend.docs_batch_update(self.id, requests)

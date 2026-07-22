from ..base import Document
from .. import _content, suggestions as _suggestions


_VIEW = {"inline": "SUGGESTIONS_INLINE", "accepted": "PREVIEW_SUGGESTIONS_ACCEPTED",
         "rejected": "PREVIEW_WITHOUT_SUGGESTIONS"}


class Doc(Document):
    """Google Docs: read (as_text/paragraphs/suggestions) + write. Accept/reject of suggestions is not
    offered — no API endpoint exists."""

    def as_text(self, suggestions: str | None = None) -> str:
        if suggestions is not None and suggestions not in _VIEW:
            raise ValueError(f"suggestions must be one of {sorted(_VIEW)} or None")
        mode = _VIEW[suggestions] if suggestions else None
        return _content.doc_text(self._backend.get_document(self.id, mode))

    @property
    def suggestions(self) -> list[_suggestions.Suggestion]:
        doc = self._backend.get_document(self.id, "SUGGESTIONS_INLINE")
        return _suggestions.extract_suggestions(doc)

    @property
    def paragraphs(self) -> list[str]:
        return _content.doc_paragraphs(self._backend.get_document(self.id))

    def replace_text(self, find: str, replace: str, match_case: bool = True) -> int:
        self._require_writable()
        resp = self._backend.docs_batch_update(self.id, [{"replaceAllText": {
            "containsText": {"text": find, "matchCase": match_case}, "replaceText": replace}}])
        return (resp.get("replies") or [{}])[0].get("replaceAllText", {}).get("occurrencesChanged", 0)

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

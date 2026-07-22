from .. import _content
from ..base import Document, occurrences_changed


class Slide:
    """One slide. `.as_text()` = its shape text; `.notes` = speaker notes."""

    def __init__(self, raw: dict):
        self._raw = raw

    def as_text(self) -> str:
        return _content.slide_text(self._raw)

    @property
    def notes(self) -> str:
        return _content.slide_notes(self._raw)

    @property
    def shape_ids(self) -> list[str]:
        """objectIds of the text-capable shapes on this slide, for use with
        `Slides.insert_text(object_id, ...)`. (Slides content is shape-addressed, unlike
        the linear index a Doc uses.)"""
        return [el["objectId"] for el in self._raw.get("pageElements", [])
                if "shape" in el and "objectId" in el]


class Slides(Document):
    """Google Slides: read (slides/as_text) + writes (deck-wide replace_text, per-shape
    insert_text). Content is shape-addressed, so text writes target a shape objectId
    (from `Slide.shape_ids`) rather than a linear index like Docs."""

    @property
    def slides(self) -> list[Slide]:
        pres = self._backend.get_presentation(self.id)
        return [Slide(s) for s in pres.get("slides", [])]

    def as_text(self) -> str:
        return "\n".join(s.as_text() for s in self.slides)

    def replace_text(self, find: str, replace: str, match_case: bool = True) -> int:
        self._require_writable()
        resp = self._backend.slides_batch_update(self.id, [{"replaceAllText": {
            "containsText": {"text": find, "matchCase": match_case}, "replaceText": replace}}])
        return occurrences_changed(resp)

    def insert_text(self, object_id: str, text: str, index: int = 0) -> None:
        """Insert `text` into the shape `object_id` at character `index`
        (symmetric to `Doc.insert_text`, but shape-addressed — see `Slide.shape_ids`)."""
        self._require_writable()
        self._backend.slides_batch_update(self.id, [{"insertText": {
            "objectId": object_id, "text": text, "insertionIndex": index}}])

    def batch_update(self, requests: list) -> dict:
        self._require_writable()
        return self._backend.slides_batch_update(self.id, requests)

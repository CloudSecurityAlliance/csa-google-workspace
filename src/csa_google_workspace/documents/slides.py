from ..base import Document
from .. import _content


class Slide:
    """One slide. `.as_text()` = its shape text; `.notes` = speaker notes."""

    def __init__(self, raw: dict):
        self._raw = raw

    def as_text(self) -> str:
        return _content.slide_text(self._raw)

    @property
    def notes(self) -> str:
        return _content.slide_notes(self._raw)


class Slides(Document):
    """Google Slides: read (slides/as_text) + deck-wide text write (replace_text)."""

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
        return resp.get("replies", [{}])[0].get("replaceAllText", {}).get("occurrencesChanged", 0)

    def batch_update(self, requests: list) -> dict:
        self._require_writable()
        return self._backend.slides_batch_update(self.id, requests)

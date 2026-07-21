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
    """Google Slides. Content read; write arrives in a later phase."""

    @property
    def slides(self) -> list[Slide]:
        pres = self._backend.get_presentation(self.id)
        return [Slide(s) for s in pres.get("slides", [])]

    def as_text(self) -> str:
        return "\n".join(s.as_text() for s in self.slides)

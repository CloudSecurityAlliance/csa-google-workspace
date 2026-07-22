"""Read Google Docs suggestions. Read-only: the Docs API has no accept/reject endpoint
(verified by probe), and exposes no suggestion author."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Literal


@dataclass
class Suggestion:
    suggestion_id: str
    kind: Literal["insertion", "deletion"]
    text: str

    def __repr__(self) -> str:
        # Redacted: omit text (document content) — see #49.
        return f"Suggestion(suggestion_id={self.suggestion_id!r}, kind={self.kind!r}, text_chars={len(self.text)})"


def _collect(el: dict, groups) -> None:
    para = el.get("paragraph")
    if para:
        for pe in para.get("elements", []):
            tr = pe.get("textRun")
            if not tr:
                continue
            content = tr.get("content", "")
            # A run may be insertion, deletion, or BOTH (a replacement uses one suggestion
            # id for a deletion run + an insertion run). Group by (id, kind) so each aspect
            # is a faithful Suggestion, rather than collapsing a replacement into one.
            for kind, key in (("insertion", "suggestedInsertionIds"),
                              ("deletion", "suggestedDeletionIds")):
                ids = tr.get(key)
                if ids:
                    sid = ids[0]
                    g = groups.setdefault((sid, kind),
                                          {"suggestion_id": sid, "kind": kind, "text": []})
                    g["text"].append(content)
        return
    table = el.get("table")
    if table:
        for row in table.get("tableRows", []):
            for cell in row.get("tableCells", []):
                for c in cell.get("content", []):
                    _collect(c, groups)


def extract_suggestions(document: dict) -> list[Suggestion]:
    groups: OrderedDict[tuple[str, str], dict] = OrderedDict()
    for el in document.get("body", {}).get("content", []):
        _collect(el, groups)
    return [Suggestion(suggestion_id=g["suggestion_id"], kind=g["kind"], text="".join(g["text"]))
            for g in groups.values()]

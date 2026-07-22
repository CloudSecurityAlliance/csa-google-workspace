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


def extract_suggestions(document: dict) -> list[Suggestion]:
    groups: "OrderedDict[str, dict]" = OrderedDict()
    for el in document.get("body", {}).get("content", []):
        para = el.get("paragraph")
        if not para:
            continue
        for pe in para.get("elements", []):
            tr = pe.get("textRun")
            if not tr:
                continue
            ins = tr.get("suggestedInsertionIds")
            dele = tr.get("suggestedDeletionIds")
            if not (ins or dele):
                continue
            sid = (ins or dele)[0]
            kind = "insertion" if ins else "deletion"
            g = groups.setdefault(sid, {"kind": kind, "text": []})
            g["text"].append(tr.get("content", ""))
    return [Suggestion(suggestion_id=sid, kind=g["kind"], text="".join(g["text"]))
            for sid, g in groups.items()]

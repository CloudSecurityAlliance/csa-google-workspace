"""Map Sheets comments to A1 cells by parsing exported XLSX comment XML.
Heuristic: no confident unique match -> no entry (caller yields location=None).
Uses defusedxml (not stdlib xml.etree): the XLSX comes from Google, but comment
text inside it is attacker-controllable, so we harden against XXE / billion-laughs."""
import io
import re
import zipfile
import defusedxml.ElementTree as ET
from collections import defaultdict

from .comments import Location


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _second(ts: str) -> str:
    """Normalize 'dT' or Drive createdTime to 'YYYY-MM-DDTHH:MM:SS' (whole second, UTC)."""
    s = ts.replace("Z", "").replace("+00:00", "")
    return s.split(".")[0]


def location_from_ref(ref: str) -> Location:
    m = re.match(r"([A-Za-z]+)(\d+)", ref or "")
    if not m:
        return Location(cell=ref, row=0, col=0)
    letters, row = m.group(1).upper(), int(m.group(2))
    col = 0
    for ch in letters:
        col = col * 26 + (ord(ch) - ord("A") + 1)
    return Location(cell=ref, row=row, col=col)


def parse_xlsx_comments(xlsx_bytes: bytes) -> list[dict]:
    z = zipfile.ZipFile(io.BytesIO(xlsx_bytes))
    persons: dict[str, str] = {}
    for name in z.namelist():
        if "/persons/" in name and name.endswith(".xml"):
            for el in ET.fromstring(z.read(name)).iter():
                if _local(el.tag) == "person":
                    persons[el.get("id")] = el.get("displayName")
    roots: list[dict] = []
    for name in z.namelist():
        if "/threadedComments/" in name and name.endswith(".xml"):
            for el in ET.fromstring(z.read(name)).iter():
                if _local(el.tag) != "threadedComment" or el.get("parentId"):
                    continue
                text = ""
                for child in el:
                    if _local(child.tag) == "text":
                        text = child.text or ""
                roots.append({
                    "ref": el.get("ref"),
                    "author": persons.get(el.get("personId")),
                    "text": text,
                    "second": _second(el.get("dT", "")),
                })
    return roots


def match_locations(comments, roots) -> dict:
    index = defaultdict(list)
    for r in roots:
        index[(r["author"], r["text"], r["second"])].append(r)
    out = {}
    for c in comments:
        author = c.author.display_name if c.author else None
        second = _second(c.created_time.isoformat()) if c.created_time else ""
        cands = index.get((author, c.content, second), [])
        if len(cands) == 1:                     # confident unique match only
            out[c.id] = location_from_ref(cands[0]["ref"])
    return out

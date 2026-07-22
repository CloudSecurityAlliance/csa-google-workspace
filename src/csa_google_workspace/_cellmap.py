"""Map Sheets comments to A1 cells by parsing exported XLSX comment XML.
Heuristic: no confident unique match -> no entry (caller yields location=None).
Uses defusedxml (not stdlib xml.etree): the XLSX comes from Google, but comment
text inside it is attacker-controllable, so we harden against XXE / billion-laughs."""
import io
import logging
import re
import zipfile
from collections import defaultdict

import defusedxml.ElementTree as ET

from .comments import Location

log = logging.getLogger(__name__)

# Defense-in-depth bounds on the XLSX parse path (SEC-1). Today the archive is
# Google-generated and export-capped ~10 MB, so these are ceilings for a future where the
# input source changes (upload/import, a different backend) and a decompression bomb or a
# hostile comment volume becomes reachable. ZipInfo.file_size is read from the archive
# header, so an oversized member is rejected *before* it is decompressed.
_MAX_MEMBER_UNCOMPRESSED = 50 * 1024 * 1024    # 50 MB per persons/threadedComments member
_MAX_TOTAL_UNCOMPRESSED = 100 * 1024 * 1024    # 100 MB across all members read
_MAX_MEMBERS = 256                              # persons + threadedComments XML members


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
    budget = _MAX_TOTAL_UNCOMPRESSED
    members = 0

    def _read(zinfo: zipfile.ZipInfo) -> bytes | None:
        """Read a member only if it stays within the per-member / total / count bounds;
        otherwise skip it (best-effort mapping degrades, never OOMs)."""
        nonlocal budget, members
        if members >= _MAX_MEMBERS:
            log.warning("XLSX comment parse hit the %d-member cap; skipping %s", _MAX_MEMBERS, zinfo.filename)
            return None
        if zinfo.file_size > _MAX_MEMBER_UNCOMPRESSED or zinfo.file_size > budget:
            log.warning("XLSX member %s (%d bytes) exceeds the parse size budget; skipping",
                        zinfo.filename, zinfo.file_size)
            return None
        members += 1
        budget -= zinfo.file_size
        return z.read(zinfo)

    persons: dict[str, str] = {}
    for zinfo in z.infolist():
        name = zinfo.filename
        if "/persons/" in name and name.endswith(".xml"):
            data = _read(zinfo)
            if data is None:
                continue
            for el in ET.fromstring(data).iter():
                if _local(el.tag) == "person":
                    persons[el.get("id")] = el.get("displayName")
    roots: list[dict] = []
    for zinfo in z.infolist():
        name = zinfo.filename
        if "/threadedComments/" in name and name.endswith(".xml"):
            data = _read(zinfo)
            if data is None:
                continue
            for el in ET.fromstring(data).iter():
                if _local(el.tag) != "threadedComment" or el.get("parentId"):
                    continue
                text = ""
                for child in el:
                    if _local(child.tag) == "text":
                        text = "".join(child.itertext())
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

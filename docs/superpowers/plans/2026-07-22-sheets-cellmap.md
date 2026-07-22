# csa-google-workspace — Phase 4 (Sheets Cell-Mapping) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Map a Sheets comment back to its **A1 cell** (`Comment.location`) — the read-side differentiator — by exporting the sheet as XLSX and parsing the comment XML, matching to Drive comments by author+content+timestamp. Plus `sheet.comments_by_cell()` and an honest `sheet.create_comment(cell=...)` deep-link.

**Architecture:** A pure `_cellmap.py` parses `xl/threadedComments/*.xml` + `xl/persons/*.xml` from exported XLSX bytes and matches Drive comments to cells. `Sheet` builds this map lazily (via the existing `backend.export_file`) and enriches each `Comment.location` through a `locate` hook on `CommentCollection`. Matching is heuristic → `None` (never a wrong guess) on ambiguity or export failure.

**Tech Stack:** Python 3.10+ (stdlib `zipfile`, **`defusedxml`** for XML parsing), `google-api-python-client`, `pytest`. Builds on Phases 1–3 (merged).

Spec §8. Empirical basis: [`experiments/sheets-cellmap/RESULTS.md`](../../../experiments/sheets-cellmap/RESULTS.md) and [`research/google-drive-comments-reference.md` §7](../../../research/google-drive-comments-reference.md).

## Global Constraints

- **Import name** `csa_google_workspace`; **`src/` layout**; **Python `>=3.10`**.
- **Read-side mapping is best-effort and heuristic.** No confident unique match ⇒ `location=None`. Export failure ⇒ `location=None` (graceful; the ~10 MB cap is generous — 120k cells = 0.69 MB measured).
- **Measured XLSX facts the parser MUST honor** (from `experiments/sheets-cellmap/RESULTS.md`):
  - Cell is `ref="B11"` on `<threadedComment>` in `xl/threadedComments/*.xml` (MS namespace `…/2018/threadedcomments`).
  - The threadedComment `id` is an **unrelated GUID** — never match on it.
  - Replies have a `parentId`; **root comments have none** — only roots carry the cell.
  - Author is `personId` → `displayName` in `xl/persons/*.xml`.
  - Match key = **(displayName, text, whole-second UTC timestamp)**. `dT` is second-precision & zoneless (`…47.00`); Drive `createdTime` is ms+`Z` (`…47.079Z`) — normalize both to `YYYY-MM-DDTHH:MM:SS`.
- **Creating a cell-*anchored* comment is impossible** via the API — `create_comment(cell=…)` makes a file-level comment with a clickable deep-link, nothing more.
- **Unit tests use `FakeBackend`** (synthetic XLSX built in-test) — no network. Real export path is integration-only.
- **XML parsing MUST use `defusedxml`, never stdlib `xml.etree` directly.** The XLSX we parse comes from Google's export, but comment *text* inside it is attacker-controllable content — stdlib parsers are vulnerable to XXE / billion-laughs. `defusedxml.ElementTree.fromstring` is a safe drop-in. Add `defusedxml` as a dependency.

---

### Task 1: `_cellmap.py` — parse XLSX comments + match to Drive comments

**Files:**
- Create: `src/csa_google_workspace/_cellmap.py`
- Modify: `src/csa_google_workspace/comments.py` (add `Location` dataclass; type `Comment.location`)
- Test: `tests/test_cellmap.py`

**Interfaces:**
- Consumes: `defusedxml` (new dependency).
- Produces:
  - `Location(cell: str, row: int, col: int, tab: str | None = None)` in `comments.py`.
  - `_cellmap.parse_xlsx_comments(xlsx_bytes: bytes) -> list[dict]` — root comments `{ref, author, text, second}`.
  - `_cellmap.match_locations(comments: list[Comment], roots: list[dict]) -> dict[str, Location]` — `comment.id → Location`, only for confident unique matches.
  - `_cellmap.location_from_ref(ref: str) -> Location`.

- [ ] **Step 1: Write the failing test** — `tests/test_cellmap.py`

```python
import io, zipfile
from datetime import datetime, timezone
from csa_google_workspace import _cellmap
from csa_google_workspace.comments import Comment, Author, Location

NS = "http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments"


def _xlsx(threaded_xml, persons_xml):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/threadedComments/threadedComment1.xml", threaded_xml)
        z.writestr("xl/persons/person.xml", persons_xml)
    return buf.getvalue()

PERSONS = f'<personList xmlns="{NS}"><person displayName="Kurt" id="P1"/></personList>'


def _threaded(entries):  # entries: list of (ref, dT, id, text, parentId|None)
    body = ""
    for ref, dT, cid, text, parent in entries:
        p = f' parentId="{parent}"' if parent else ""
        body += (f'<threadedComment ref="{ref}" dT="{dT}" personId="P1" id="{cid}"{p}>'
                 f'<text>{text}</text></threadedComment>')
    return f'<ThreadedComments xmlns="{NS}">{body}</ThreadedComments>'


def _comment(cid, content, dt):
    return Comment(id=cid, author=Author("Kurt", None, False, None), content=content,
                   html_content=content, quoted_text=None, anchor=None, location=None,
                   resolved=False, deleted=False, created_time=dt, modified_time=dt, replies=[])


def test_location_from_ref_computes_row_col():
    loc = _cellmap.location_from_ref("B11")
    assert (loc.cell, loc.row, loc.col) == ("B11", 11, 2)


def test_parse_extracts_roots_and_skips_replies():
    xml = _threaded([("B11", "2026-07-20T23:05:59.00", "R1", "hi there", None),
                     ("B11", "2026-07-20T23:06:00.00", "R2", "a reply", "R1")])
    roots = _cellmap.parse_xlsx_comments(_xlsx(xml, PERSONS))
    assert len(roots) == 1
    assert roots[0]["ref"] == "B11" and roots[0]["author"] == "Kurt" and roots[0]["text"] == "hi there"


def test_match_by_author_content_second():
    xml = _threaded([("B11", "2026-07-20T23:05:59.00", "R1", "hi there", None)])
    roots = _cellmap.parse_xlsx_comments(_xlsx(xml, PERSONS))
    c = _comment("cid1", "hi there", datetime(2026, 7, 20, 23, 5, 59, 479000, tzinfo=timezone.utc))
    out = _cellmap.match_locations([c], roots)
    assert out["cid1"].cell == "B11"


def test_ambiguous_duplicate_yields_no_match():
    xml = _threaded([("B11", "2026-07-20T23:05:59.00", "R1", "dup", None),
                     ("C22", "2026-07-20T23:05:59.00", "R2", "dup", None)])
    roots = _cellmap.parse_xlsx_comments(_xlsx(xml, PERSONS))
    c = _comment("cid1", "dup", datetime(2026, 7, 20, 23, 5, 59, tzinfo=timezone.utc))
    assert _cellmap.match_locations([c], roots) == {}   # ambiguous -> no guess
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cellmap.py -v`
Expected: FAIL — `ModuleNotFoundError: csa_google_workspace._cellmap` / `Location` missing.

- [ ] **Step 3: Add `Location`** — append to `src/csa_google_workspace/comments.py` (near the top, after imports):

```python
@dataclass
class Location:
    cell: str
    row: int
    col: int
    tab: str | None = None
```
Also change the `Comment.location` field annotation from `location: object | None` to `location: "Location | None"` (same default `None`).

- [ ] **Step 3b: Add the `defusedxml` dependency** — in `pyproject.toml`, add `"defusedxml>=0.7"` to `[project].dependencies` (alongside the google packages), then re-run `pip install -e ".[dev]"`.

- [ ] **Step 4: Write** — `src/csa_google_workspace/_cellmap.py`

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_cellmap.py -v`
Expected: PASS (4 tests). Then `pytest -q`.

- [ ] **Step 6: Commit**

```bash
git add src/csa_google_workspace/_cellmap.py src/csa_google_workspace/comments.py tests/test_cellmap.py
git commit -m "feat: XLSX comment->A1 cell-map parser + matcher (Location)"
```

---

### Task 2: Wire cell locations into `Sheet` comments

**Files:**
- Modify: `src/csa_google_workspace/comments.py` (`CommentCollection` gains a `locate` hook)
- Modify: `src/csa_google_workspace/base.py` (`CommentsMixin.comments` passes `locate`)
- Modify: `src/csa_google_workspace/documents/sheet.py` (`_cell_map`, `_locate_comment`, `comments_by_cell`)
- Test: `tests/test_sheet_cellmap.py`

**Interfaces:**
- Consumes: `_cellmap` (Task 1), `backend.export_file` + `backend.list_comments`.
- Produces:
  - `CommentCollection(backend, file_id, read_only, locate=None)`; `_wrap` sets `c.location = locate(d)` when `locate` given.
  - `CommentsMixin.comments` passes `locate=getattr(self, "_locate_comment", None)`.
  - `Sheet._cell_map() -> dict[str, Location]` (cached per instance; export→parse→match).
  - `Sheet._locate_comment(raw: dict) -> Location | None`.
  - `Sheet.comments_by_cell(cell: str) -> list[Comment]`.

- [ ] **Step 1: Write the failing test** — `tests/test_sheet_cellmap.py`

```python
import io, zipfile
from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend

SHEET = "application/vnd.google-apps.spreadsheet"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
NS = "http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments"
META = {"s": {"id": "s", "name": "S", "mimeType": SHEET, "webViewLink": "https://x/spreadsheets/d/s/edit"}}


def _xlsx(ref, author, text, dT):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/persons/person.xml",
                   f'<personList xmlns="{NS}"><person displayName="{author}" id="P1"/></personList>')
        z.writestr("xl/threadedComments/threadedComment1.xml",
                   f'<ThreadedComments xmlns="{NS}"><threadedComment ref="{ref}" dT="{dT}" '
                   f'personId="P1" id="G1"><text>{text}</text></threadedComment></ThreadedComments>')
    return buf.getvalue()


def _sheet_with_mapped_comment():
    b = FakeBackend(META)
    c = b.create_comment("s", "check West")        # FakeBackend sets author "Test User", createdTime 2026-01-01T00:00:00Z
    b._exports[("s", XLSX)] = _xlsx("B11", "Test User", "check West", "2026-01-01T00:00:00.00")
    return Workspace(b).open("s"), c["id"]


def test_comment_location_populated():
    sheet, cid = _sheet_with_mapped_comment()
    assert sheet.comments.get(cid).location.cell == "B11"


def test_comments_by_cell():
    sheet, cid = _sheet_with_mapped_comment()
    hits = sheet.comments_by_cell("B11")
    assert [c.id for c in hits] == [cid]
    assert sheet.comments_by_cell("Z99") == []


def test_location_none_when_no_export_match():
    b = FakeBackend(META)
    c = b.create_comment("s", "unmapped")
    b._exports[("s", XLSX)] = _xlsx("B11", "Someone Else", "different", "2026-01-01T00:00:00.00")
    sheet = Workspace(b).open("s")
    assert sheet.comments.get(c["id"]).location is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sheet_cellmap.py -v`
Expected: FAIL — `AttributeError: 'Sheet' object has no attribute 'comments_by_cell'` / location is None.

- [ ] **Step 3: Add the `locate` hook to `CommentCollection`** — in `comments.py`, update `__init__` and `_wrap`:

```python
    def __init__(self, backend, file_id: str, read_only: bool, locate=None):
        self._backend = backend
        self._file_id = file_id
        self._read_only = read_only
        self._locate = locate
```
and in `_wrap`, after building `c` and before returning (after the reply-ref loop):
```python
        if self._locate is not None:
            c.location = self._locate(d)
```

- [ ] **Step 4: Pass `locate` from `CommentsMixin`** — in `base.py`, change the `comments` property:

```python
    @property
    def comments(self) -> CommentCollection:
        return CommentCollection(self._backend, self.id, self.read_only,
                                 locate=getattr(self, "_locate_comment", None))
```
(`create_comment` still uses `self.comments._wrap(d)`, which now also runs `locate` — fine.)

- [ ] **Step 5: Implement the `Sheet` map** — `documents/sheet.py`:

```python
from ..base import Document
from .. import _cellmap

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class Sheet(Document):
    """Google Sheets. Comment->A1 cell mapping is best-effort (XLSX export + match)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cell_map_cache = None

    # ... existing tabs / values / as_text stay ...

    def _cell_map(self) -> dict:
        if self._cell_map_cache is None:
            try:
                xlsx = self._backend.export_file(self.id, _XLSX)
                roots = _cellmap.parse_xlsx_comments(xlsx)
                raw = self._backend.list_comments(self.id, include_deleted=False)
                from ..comments import Comment
                comments = [Comment.from_api(d) for d in raw]
                self._cell_map_cache = _cellmap.match_locations(comments, roots)
            except Exception:
                self._cell_map_cache = {}      # degrade: no locations
        return self._cell_map_cache

    def _locate_comment(self, raw: dict):
        return self._cell_map().get(raw.get("id"))

    def comments_by_cell(self, cell: str) -> list:
        return [c for c in self.comments.all() if c.location and c.location.cell == cell]

    def reload(self) -> None:
        self._cell_map_cache = None
```
Keep the existing `tabs`/`values`/`as_text` methods intact — only add the above.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_sheet_cellmap.py -v`
Expected: PASS (3 tests). Then `pytest -q` (all prior green — the `locate` hook defaults to `None` for Doc/Slides).

- [ ] **Step 7: Commit**

```bash
git add src/csa_google_workspace/comments.py src/csa_google_workspace/base.py src/csa_google_workspace/documents/sheet.py tests/test_sheet_cellmap.py
git commit -m "feat: populate Comment.location for Sheets + comments_by_cell"
```

---

### Task 3: `Sheet.create_comment(cell=...)` deep-link + `as_text` range-quoting

**Files:**
- Modify: `src/csa_google_workspace/documents/sheet.py`
- Test: `tests/test_sheet_create_comment.py`

**Interfaces:**
- Consumes: `backend.get_spreadsheet` (for gid), `create_comment` (base).
- Produces:
  - `Sheet.create_comment(text: str, cell: str | None = None) -> Comment` — plain when `cell` is None; else appends a clickable `#gid=<gid>&range=<cell>` deep-link to the body (file-level comment; honest about being a link, not an anchor).
  - `Sheet._quote_tab(title: str) -> str` and `as_text` uses it (fixes the deferred unquoted-range bug).

- [ ] **Step 1: Write the failing test** — `tests/test_sheet_create_comment.py`

```python
from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend

SHEET = "application/vnd.google-apps.spreadsheet"
META = {"s": {"id": "s", "name": "S", "mimeType": SHEET, "webViewLink": "https://x/spreadsheets/d/s/edit"}}


def _sheet(tabs):
    b = FakeBackend(META, spreadsheets={"s": {"sheets": [
        {"properties": {"sheetId": sid, "title": t}} for t, sid in tabs]}},
        values={("s", t if " " not in t else f"'{t}'"): [["a", "b"]] for t, _ in tabs})
    return Workspace(b).open("s")


def test_create_comment_with_cell_embeds_deeplink():
    s = _sheet([("Sheet1", 0)])
    c = s.create_comment("check this", cell="B11")
    assert "gid=0" in c.content and "range=B11" in c.content and "check this" in c.content


def test_create_comment_without_cell_is_plain():
    s = _sheet([("Sheet1", 0)])
    c = s.create_comment("just a note")
    assert c.content == "just a note"


def test_as_text_quotes_tab_with_spaces():
    s = _sheet([("Q1 Budget", 0)])   # values fixture keyed by the quoted range
    # should not raise / should read via the quoted range
    assert s.as_text() == "a\tb"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sheet_create_comment.py -v`
Expected: FAIL — `create_comment()` takes no `cell` / `as_text` uses unquoted range.

- [ ] **Step 3: Implement** — add to `Sheet` and adjust `as_text`:

```python
    def _quote_tab(self, title: str) -> str:
        return title if title.replace("_", "").isalnum() else f"'{title}'"

    def _gid(self, title=None):
        sheets = self._backend.get_spreadsheet(self.id).get("sheets", [])
        for s in sheets:
            props = s.get("properties", {})
            if title is None or props.get("title") == title:
                return props.get("sheetId", 0)
        return 0

    def create_comment(self, text: str, cell: str | None = None):
        if cell is None:
            return super().create_comment(text)
        gid = self._gid()
        link = f"{self.url.split('/edit')[0]}/edit#gid={gid}&range={cell}"
        return super().create_comment(f"{text}\n\n{link}")
```
And change `as_text` to quote the tab:
```python
    def as_text(self) -> str:
        rng = self._quote_tab(self.tabs[0]) if self.tabs else "A1:Z1000"
        rows = self._backend.get_values(self.id, rng)
        return "\n".join("\t".join(str(c) for c in row) for row in rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sheet_create_comment.py -v`
Expected: PASS (3 tests). Then `pytest -q`.

- [ ] **Step 5: Commit**

```bash
git add src/csa_google_workspace/documents/sheet.py tests/test_sheet_create_comment.py
git commit -m "feat: Sheet.create_comment(cell=) deep-link + as_text tab-name quoting"
```

---

### Task 4: Gated live Sheets cell-mapping integration

**Files:**
- Modify: `tests/integration/test_all_types_live.py` (add a cell-mapping test)

**Interfaces:**
- Consumes: the real export→parse→match pipeline.
- Produces: a gated test that creates a throwaway Sheet, adds an API comment (which lands on A1), and asserts the library maps it to a cell (A1) via the real XLSX export. (UI-placed multi-cell comments need manual setup; documented — this proves the live pipeline end-to-end on A1.)

- [ ] **Step 1: Add the gated test** — append to `tests/integration/test_all_types_live.py`

```python
def test_sheet_cell_mapping_live():
    from csa_google_workspace import Sheet
    ws = _ws()
    with _throwaway(ws, "application/vnd.google-apps.spreadsheet", "E2E-CellMap-THROWAWAY") as fid:
        ws._backend._services.sheets.spreadsheets().values().update(
            spreadsheetId=fid, range="A1", valueInputOption="RAW",
            body={"values": [["hdr"]]}).execute()
        s = ws.open(fid)
        assert isinstance(s, Sheet)
        c = s.create_comment("map me")           # API comment -> lands on A1 in the export
        loc = s.comments.get(c.id).location
        assert loc is not None and loc.cell == "A1", f"expected A1, got {loc}"
        c.delete()
```

- [ ] **Step 2: Verify it SKIPS cleanly without credentials**

Run: `pytest tests/integration/ -v`
Expected: 4 skipped. Then `pytest -q` — full unit suite green + 4 skipped.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_all_types_live.py
git commit -m "test: gated live Sheets cell-mapping (API comment -> A1)"
```

---

## Notes for later phases (not this plan)
- **Content write** (`replace_text`/`insert`/`delete` + `batch_update`, `read_only`-gated, index-safe).
- **Docs suggestions read** (`doc.suggestions`, `doc.as_text(suggestions="accepted"|"rejected")`).
- **Tab-name resolution for `Location.tab`** — currently `None`; resolving the threadedComment part → worksheet name (workbook.xml + rels) is a follow-up.
- Real export/parse path exercised by Task 4's gated suite, not unit tests.

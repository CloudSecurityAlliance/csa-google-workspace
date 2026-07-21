# csa-google-workspace — Phase 3 (Content Read) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read document **content** (text + light structure) across Docs/Sheets/Slides, plus a uniform Drive `export` — so a caller can pull a file's content for context alongside its comments. **Read only; no writing.**

**Architecture:** Content is the *variant axis*: each type uses its own Google API (Docs v1 `documents.get`, Sheets v4 `spreadsheets.values`/`spreadsheets.get`, Slides v1 `presentations.get`), plus Drive `files.export` (uniform). The `Backend` gains content-read methods (`ApiBackend` = real calls via `_errors.call`; `FakeBackend` = injected fixtures). A uniform `as_text()`/`export()` lives on `Document`; type-specific accessors live on the subclasses.

**Tech Stack:** Python 3.10+, `google-api-python-client`, `pytest`. Builds on Phases 1–2 (merged).

Spec: [`docs/superpowers/specs/2026-07-20-csa-google-workspace-design.md`](../specs/2026-07-20-csa-google-workspace-design.md) §6.

## Global Constraints

- **Import name** `csa_google_workspace`; **`src/` layout**; **Python `>=3.10`**.
- **Read only** — this phase adds NO write/mutation. Content *write* is a later phase.
- **Unit tests use `FakeBackend`** with injected content fixtures — no network, no credentials. Real API paths are covered only by the **gated integration suite** (`CSA_GW_INTEGRATION=1`).
- **`as_text()` is a best-effort convenience, not a uniform contract** (per spec §6): it means different things per type and can be large; do not over-promise it.
- Text extraction is **plain text only** — join text runs / cell values / shape text. Skip images, charts, embedded objects, and formatting. Tables (Docs) contribute their cell text.
- **No caching, no persistent storage** (carried from Phase 1/2 defaults).

---

### Task 1: Backend content-read methods + `Document.export`

**Files:**
- Modify: `src/csa_google_workspace/backend.py`
- Modify: `src/csa_google_workspace/base.py` (add `export`)
- Test: `tests/test_backend_content.py`

**Interfaces:**
- Consumes: `_errors.call`, `exceptions.NotFoundError`.
- Produces (added to the `Backend` protocol and BOTH backends):
  - `export_file(file_id: str, mime_type: str) -> bytes`
  - `get_document(file_id: str) -> dict`
  - `get_spreadsheet(file_id: str) -> dict`
  - `get_values(file_id: str, a1_range: str) -> list[list]`
  - `get_presentation(file_id: str) -> dict`
  - `FakeBackend.__init__` gains optional fixture kwargs: `documents=None, spreadsheets=None, values=None, presentations=None, exports=None` (each a `dict` keyed by `file_id`; missing → `NotFoundError`, except `get_values` returns `[]` for an absent range).
  - `Document.export(mime_type) -> bytes` (uniform, delegates to `backend.export_file`).

- [ ] **Step 1: Write the failing test** — `tests/test_backend_content.py`

```python
import pytest
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace import exceptions as exc

DOC = "application/vnd.google-apps.document"
META = {"f": {"id": "f", "name": "F", "mimeType": DOC, "webViewLink": "https://x/document/d/f/edit"}}


def be():
    return FakeBackend(
        META,
        documents={"f": {"title": "F", "body": {"content": []}}},
        spreadsheets={"f": {"sheets": [{"properties": {"sheetId": 0, "title": "Sheet1"}}]}},
        values={("f", "Sheet1!A1:B2"): [["a", "b"], ["c", "d"]]},
        presentations={"f": {"slides": []}},
        exports={("f", "application/pdf"): b"%PDF-1.4 fake"},
    )


def test_get_document_returns_fixture():
    assert be().get_document("f")["title"] == "F"


def test_get_document_missing_raises():
    with pytest.raises(exc.NotFoundError):
        be().get_document("nope")


def test_get_values_returns_grid_and_absent_is_empty():
    b = be()
    assert b.get_values("f", "Sheet1!A1:B2") == [["a", "b"], ["c", "d"]]
    assert b.get_values("f", "Sheet1!Z1:Z9") == []


def test_get_spreadsheet_and_presentation():
    b = be()
    assert b.get_spreadsheet("f")["sheets"][0]["properties"]["title"] == "Sheet1"
    assert be().get_presentation("f") == {"slides": []}


def test_export_returns_bytes():
    assert be().export_file("f", "application/pdf") == b"%PDF-1.4 fake"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_backend_content.py -v`
Expected: FAIL — `TypeError` (FakeBackend takes no `documents=` kwarg) / `AttributeError` (no `get_document`).

- [ ] **Step 3: Extend the `Backend` protocol** — add to the `Backend` Protocol class in `backend.py`:

```python
    def export_file(self, file_id: str, mime_type: str) -> bytes: ...
    def get_document(self, file_id: str) -> dict: ...
    def get_spreadsheet(self, file_id: str) -> dict: ...
    def get_values(self, file_id: str, a1_range: str) -> list: ...
    def get_presentation(self, file_id: str) -> dict: ...
```

- [ ] **Step 4: Extend `FakeBackend`.** Update `FakeBackend.__init__` signature and store the fixtures, then add the methods:

```python
    def __init__(self, files, *, documents=None, spreadsheets=None,
                 values=None, presentations=None, exports=None):
        self._files = files
        self._comments = {}
        self._seq = 0
        self._documents = documents or {}
        self._spreadsheets = spreadsheets or {}
        self._values = values or {}
        self._presentations = presentations or {}
        self._exports = exports or {}

    def _fixture(self, store, key, kind):
        # `copy` is already imported at the top of backend.py (from the Phase-2 deep-copy fix).
        if key not in store:
            raise exc.NotFoundError(f"{kind} '{key}' not found")
        return copy.deepcopy(store[key])

    def export_file(self, file_id, mime_type):
        return self._fixture(self._exports, (file_id, mime_type), "export")

    def get_document(self, file_id):
        return self._fixture(self._documents, file_id, "document")

    def get_spreadsheet(self, file_id):
        return self._fixture(self._spreadsheets, file_id, "spreadsheet")

    def get_values(self, file_id, a1_range):
        return copy.deepcopy(self._values.get((file_id, a1_range), []))

    def get_presentation(self, file_id):
        return self._fixture(self._presentations, file_id, "presentation")
```
(Keep the existing `self._comments`/`self._seq` init — merge the two lines into the new `__init__` exactly as shown. Do not remove the existing comment methods.)

- [ ] **Step 5: Implement `ApiBackend` methods.** Add to `ApiBackend` (real calls via `_errors.call`):

```python
    def export_file(self, file_id, mime_type):
        return _errors.call(self._services.drive.files()
                            .export(fileId=file_id, mimeType=mime_type).execute)

    def get_document(self, file_id):
        return _errors.call(self._services.docs.documents().get(documentId=file_id).execute)

    def get_spreadsheet(self, file_id):
        return _errors.call(self._services.sheets.spreadsheets()
                            .get(spreadsheetId=file_id,
                                 fields="sheets(properties(sheetId,title))").execute)

    def get_values(self, file_id, a1_range):
        resp = _errors.call(self._services.sheets.spreadsheets().values()
                            .get(spreadsheetId=file_id, range=a1_range).execute)
        return resp.get("values", [])

    def get_presentation(self, file_id):
        return _errors.call(self._services.slides.presentations().get(presentationId=file_id).execute)
```

- [ ] **Step 6: Add `Document.export`** — in `base.py`, add to `Document`:

```python
    def export(self, mime_type: str) -> bytes:
        return self._backend.export_file(self.id, mime_type)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_backend_content.py -v`
Expected: PASS (5 tests). Then `pytest -q` — all prior green (existing FakeBackend callers still pass since the new kwargs are keyword-only with defaults).

- [ ] **Step 8: Commit**

```bash
git add src/csa_google_workspace/backend.py src/csa_google_workspace/base.py tests/test_backend_content.py
git commit -m "feat: content-read backend methods + Document.export"
```

---

### Task 2: `Doc` content — `as_text` + `paragraphs`

**Files:**
- Modify: `src/csa_google_workspace/documents/doc.py`
- Create: `src/csa_google_workspace/_content.py` (shared text-walk helpers)
- Test: `tests/test_doc_content.py`

**Interfaces:**
- Consumes: `backend.get_document` (Task 1).
- Produces:
  - `_content.doc_text(document: dict) -> str` — plain text of a Docs `documents.get` response (paragraphs + table cell text, in order).
  - `Doc.as_text() -> str`; `Doc.paragraphs -> list[str]` (one string per top-level paragraph).

- [ ] **Step 1: Write the failing test** — `tests/test_doc_content.py`

```python
from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
META = {"d": {"id": "d", "name": "D", "mimeType": DOC, "webViewLink": "https://x/document/d/d/edit"}}
DOCUMENT = {"title": "D", "body": {"content": [
    {"paragraph": {"elements": [{"textRun": {"content": "Hello world\n"}}]}},
    {"paragraph": {"elements": [{"textRun": {"content": "Second para\n"}}]}},
    {"table": {"tableRows": [{"tableCells": [
        {"content": [{"paragraph": {"elements": [{"textRun": {"content": "cell1\n"}}]}}]},
        {"content": [{"paragraph": {"elements": [{"textRun": {"content": "cell2\n"}}]}}]},
    ]}]}},
]}}


def doc():
    return Workspace(FakeBackend(META, documents={"d": DOCUMENT})).open("d")


def test_as_text_joins_paragraphs_and_table_cells():
    t = doc().as_text()
    assert "Hello world" in t and "Second para" in t
    assert "cell1" in t and "cell2" in t


def test_paragraphs_are_split():
    ps = doc().paragraphs
    assert ps[0] == "Hello world" and ps[1] == "Second para"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_doc_content.py -v`
Expected: FAIL — `AttributeError: 'Doc' object has no attribute 'as_text'` (base has none yet) / `_content` missing.

- [ ] **Step 3: Write** — `src/csa_google_workspace/_content.py`

```python
"""Plain-text extraction helpers for Docs/Slides API responses. Text runs only."""


def _para_text(paragraph: dict) -> str:
    return "".join(e.get("textRun", {}).get("content", "")
                   for e in paragraph.get("elements", []))


def _element_text(el: dict) -> str:
    if "paragraph" in el:
        return _para_text(el["paragraph"])
    if "table" in el:
        parts = []
        for row in el["table"].get("tableRows", []):
            for cell in row.get("tableCells", []):
                parts.extend(_element_text(c) for c in cell.get("content", []))
        return "".join(parts)
    return ""


def doc_text(document: dict) -> str:
    return "".join(_element_text(el) for el in document.get("body", {}).get("content", []))


def doc_paragraphs(document: dict) -> list[str]:
    out = []
    for el in document.get("body", {}).get("content", []):
        if "paragraph" in el:
            out.append(_para_text(el["paragraph"]).rstrip("\n"))
    return out
```

- [ ] **Step 4: Implement `Doc`** — `src/csa_google_workspace/documents/doc.py`:

```python
from ..base import Document
from .. import _content


class Doc(Document):
    """Google Docs. Content read; write + suggestions arrive in later phases."""

    def as_text(self) -> str:
        return _content.doc_text(self._backend.get_document(self.id))

    @property
    def paragraphs(self) -> list[str]:
        return _content.doc_paragraphs(self._backend.get_document(self.id))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_doc_content.py -v`
Expected: PASS (2 tests). Then `pytest -q`.

- [ ] **Step 6: Commit**

```bash
git add src/csa_google_workspace/_content.py src/csa_google_workspace/documents/doc.py tests/test_doc_content.py
git commit -m "feat: Doc.as_text + Doc.paragraphs (Docs content read)"
```

---

### Task 3: `Sheet` content — `tabs`, `values`, `as_text`

**Files:**
- Modify: `src/csa_google_workspace/documents/sheet.py`
- Test: `tests/test_sheet_content.py`

**Interfaces:**
- Consumes: `backend.get_spreadsheet` + `backend.get_values` (Task 1).
- Produces:
  - `Sheet.tabs -> list[str]` (worksheet titles).
  - `Sheet.values(a1_range: str) -> list[list]`.
  - `Sheet.as_text() -> str` — the given/first tab's grid, tab-joined rows, newline-joined.

- [ ] **Step 1: Write the failing test** — `tests/test_sheet_content.py`

```python
from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend

SHEET = "application/vnd.google-apps.spreadsheet"
META = {"s": {"id": "s", "name": "S", "mimeType": SHEET, "webViewLink": "https://x/spreadsheets/d/s/edit"}}


def sheet():
    return Workspace(FakeBackend(
        META,
        spreadsheets={"s": {"sheets": [{"properties": {"sheetId": 0, "title": "Sheet1"}},
                                        {"properties": {"sheetId": 1, "title": "Data"}}]}},
        values={("s", "Sheet1"): [["h1", "h2"], ["1", "2"]]},
    )).open("s")


def test_tabs_lists_titles():
    assert sheet().tabs == ["Sheet1", "Data"]


def test_values_returns_grid():
    assert sheet().values("Sheet1") == [["h1", "h2"], ["1", "2"]]


def test_as_text_joins_rows_and_cells():
    t = sheet().as_text()
    assert "h1\th2" in t and "1\t2" in t
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sheet_content.py -v`
Expected: FAIL — `AttributeError: 'Sheet' object has no attribute 'tabs'`.

- [ ] **Step 3: Implement `Sheet`** — `src/csa_google_workspace/documents/sheet.py`:

```python
from ..base import Document


class Sheet(Document):
    """Google Sheets. Content read; cell-mapping + write arrive in later phases."""

    @property
    def tabs(self) -> list[str]:
        ss = self._backend.get_spreadsheet(self.id)
        return [s["properties"]["title"] for s in ss.get("sheets", [])]

    def values(self, a1_range: str) -> list:
        return self._backend.get_values(self.id, a1_range)

    def as_text(self) -> str:
        rng = self.tabs[0] if self.tabs else "A1:Z1000"
        rows = self._backend.get_values(self.id, rng)
        return "\n".join("\t".join(str(c) for c in row) for row in rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sheet_content.py -v`
Expected: PASS (3 tests). Then `pytest -q`.

- [ ] **Step 5: Commit**

```bash
git add src/csa_google_workspace/documents/sheet.py tests/test_sheet_content.py
git commit -m "feat: Sheet.tabs + values + as_text (Sheets content read)"
```

---

### Task 4: `Slides` content — `slides`, `as_text`, notes

**Files:**
- Modify: `src/csa_google_workspace/documents/slides.py`
- Modify: `src/csa_google_workspace/_content.py` (add slide helpers)
- Test: `tests/test_slides_content.py`

**Interfaces:**
- Consumes: `backend.get_presentation` (Task 1).
- Produces:
  - `_content.slide_text(slide: dict) -> str` and `_content.slide_notes(slide: dict) -> str`.
  - `Slides.slides -> list[Slide]` where `Slide` has `.as_text() -> str` and `.notes -> str`.
  - `Slides.as_text() -> str` — all slides' text joined.

- [ ] **Step 1: Write the failing test** — `tests/test_slides_content.py`

```python
from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend

PRES = "application/vnd.google-apps.presentation"
META = {"p": {"id": "p", "name": "P", "mimeType": PRES, "webViewLink": "https://x/presentation/d/p/edit"}}


def _shape(text):
    return {"shape": {"text": {"textElements": [{"textRun": {"content": text}}]}}}


PRESENTATION = {"slides": [
    {"pageElements": [_shape("Title slide\n"), _shape("subtitle\n")]},
    {"pageElements": [_shape("Second slide\n")]},
]}


def slides():
    return Workspace(FakeBackend(META, presentations={"p": PRESENTATION})).open("p")


def test_slides_list_and_per_slide_text():
    s = slides().slides
    assert len(s) == 2
    assert "Title slide" in s[0].as_text() and "subtitle" in s[0].as_text()
    assert "Second slide" in s[1].as_text()


def test_deck_as_text_joins_all_slides():
    t = slides().as_text()
    assert "Title slide" in t and "Second slide" in t
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_slides_content.py -v`
Expected: FAIL — `AttributeError: 'Slides' object has no attribute 'slides'`.

- [ ] **Step 3: Add slide helpers** — append to `src/csa_google_workspace/_content.py`:

```python
def slide_text(slide: dict) -> str:
    parts = []
    for pe in slide.get("pageElements", []):
        for te in pe.get("shape", {}).get("text", {}).get("textElements", []):
            parts.append(te.get("textRun", {}).get("content", ""))
    return "".join(parts)


def slide_notes(slide: dict) -> str:
    notes = (slide.get("slideProperties", {}).get("notesPage", {}))
    return "".join(
        te.get("textRun", {}).get("content", "")
        for pe in notes.get("pageElements", [])
        for te in pe.get("shape", {}).get("text", {}).get("textElements", [])
    )
```

- [ ] **Step 4: Implement `Slides`** — `src/csa_google_workspace/documents/slides.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_slides_content.py -v`
Expected: PASS (2 tests). Then `pytest -q`.

- [ ] **Step 6: Commit**

```bash
git add src/csa_google_workspace/_content.py src/csa_google_workspace/documents/slides.py tests/test_slides_content.py
git commit -m "feat: Slides.slides + as_text + per-slide notes (Slides content read)"
```

---

### Task 5: Extend the gated integration suite with content reads

**Files:**
- Modify: `tests/integration/test_content_live.py` (new file)

**Interfaces:**
- Consumes: the whole content-read API against real Google files.
- Produces: a gated test (skipped unless `CSA_GW_INTEGRATION=1` + `CSA_GW_CLIENT_SECRETS`) that creates a throwaway Doc, verifies `as_text`/`paragraphs`/`export` read back real content, then trashes it.

- [ ] **Step 1: Write the gated test** — `tests/integration/test_content_live.py`

```python
import os
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CSA_GW_INTEGRATION") != "1",
    reason="set CSA_GW_INTEGRATION=1 and CSA_GW_CLIENT_SECRETS to run live Google tests",
)


def test_doc_content_read_live():
    from csa_google_workspace import Workspace
    ws = Workspace.from_oauth(os.environ["CSA_GW_CLIENT_SECRETS"])
    drive = ws._backend._services.drive
    f = drive.files().create(
        body={"name": "PROBE-content-THROWAWAY",
              "mimeType": "application/vnd.google-apps.document"},
        fields="id").execute()
    fid = f["id"]
    try:
        # seed some text via the Docs API (write is not in the library yet, so use the raw client)
        ws._backend._services.docs.documents().batchUpdate(
            documentId=fid,
            body={"requests": [{"insertText": {"location": {"index": 1},
                                               "text": "Integration content line."}}]}).execute()
        doc = ws.open(fid)
        assert "Integration content line." in doc.as_text()
        assert any("Integration content line." in p for p in doc.paragraphs)
        assert doc.export("application/pdf")[:4] == b"%PDF"
    finally:
        drive.files().update(fileId=fid, body={"trashed": True}).execute()
```

- [ ] **Step 2: Verify it SKIPS cleanly without credentials**

Run: `pytest tests/integration/ -v`
Expected: 2 skipped (this + the Phase-2 comment lifecycle), reasons shown. Then `pytest -q` — full unit suite green, 2 skipped.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_content_live.py
git commit -m "test: gated live content-read integration (Docs text/paragraphs/export)"
```

---

## Notes for later phases (not this plan)
- **Content write** (`replace_text`/`append_text`/`insert`/`delete` + `batch_update`, `read_only`-gated, back-to-front index safety for Docs/Slides).
- **Sheets cell-mapping** populates `Comment.location` via XLSX export (`export_file` from Task 1 is the entry point) + `comments_by_cell`.
- **Docs suggestions read** (`doc.suggestions`, `doc.as_text(suggestions="accepted"|"rejected")`).
- Real API call shapes here are exercised by Task 5's gated suite, not the unit tests.

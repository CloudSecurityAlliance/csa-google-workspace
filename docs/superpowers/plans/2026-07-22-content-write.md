# csa-google-workspace — Phase 5 (Content Write) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write document **content** across Docs/Sheets/Slides — high-level helpers (`replace_text`, `append_text`, cell `update`) plus a raw `batch_update` escape hatch per type — all gated behind `read_only`.

**Architecture:** Content write is the *variant axis*: each type's helpers build the correct `batchUpdate` request(s) for its API (Docs v1, Sheets v4 values, Slides v1). The `Backend` gains write methods (`ApiBackend` = real calls via `_errors.call`; `FakeBackend` = records the requests, so unit tests assert the exact payload the library would send — the thing that 400s live if wrong). Every write raises `ReadOnlyError` when the workspace is `read_only`.

**Tech Stack:** Python 3.10+, `google-api-python-client`, `pytest`. Builds on Phases 1–4 (merged).

Spec §6 (write half).

## Global Constraints

- **Import name** `csa_google_workspace`; **`src/` layout**; **Python `>=3.10`**.
- **`read_only` gates every write** — a mutating content call raises `ReadOnlyError` when `self.read_only`, before any backend call.
- **High-level helpers each build a SINGLE `batchUpdate` request** (so no cross-request index reordering is needed); `batch_update(requests)` is the raw escape hatch where the caller owns ordering and coupling to google-api request shapes (accepted trade-off, per spec §6).
- **Unit tests use `FakeBackend`** which **records** write requests (no network); tests assert the recorded request shape. Real write calls are covered only by the gated integration suite.
- Slides per-shape/positional editing stays out (spec §14.3): only deck-wide `replace_text` + raw `batch_update`.

---

### Task 1: Backend write methods + `Document._require_writable`

**Files:**
- Modify: `src/csa_google_workspace/backend.py`
- Modify: `src/csa_google_workspace/base.py` (add `_require_writable`)
- Test: `tests/test_backend_write.py`

**Interfaces:**
- Consumes: `_errors.call`, `exceptions.ReadOnlyError`.
- Produces (on the `Backend` protocol + both backends):
  - `docs_batch_update(file_id, requests: list) -> dict`
  - `sheets_values_update(file_id, a1_range: str, values: list) -> dict`
  - `sheets_values_clear(file_id, a1_range: str) -> dict`
  - `sheets_batch_update(file_id, requests: list) -> dict`
  - `slides_batch_update(file_id, requests: list) -> dict`
  - `FakeBackend` records each call to `self._writes` (a list of tuples) and, for `sheets_values_update`, also updates its `_values` fixture; `sheets_values_clear` pops it.
  - `Document._require_writable()` raises `ReadOnlyError` when `self.read_only`.

- [ ] **Step 1: Write the failing test** — `tests/test_backend_write.py`

```python
import pytest
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
META = {"f": {"id": "f", "name": "F", "mimeType": DOC, "webViewLink": "https://x/document/d/f/edit"}}


def be():
    return FakeBackend(META)


def test_docs_batch_update_records():
    b = be()
    b.docs_batch_update("f", [{"insertText": {"location": {"index": 1}, "text": "hi"}}])
    assert b._writes == [("f", "docs", [{"insertText": {"location": {"index": 1}, "text": "hi"}}])]


def test_sheets_values_update_records_and_updates_fixture():
    b = be()
    b.sheets_values_update("f", "Sheet1!A1", [["x", "y"]])
    assert ("f", "sheets_values_update", "Sheet1!A1", [["x", "y"]]) in b._writes
    assert b.get_values("f", "Sheet1!A1") == [["x", "y"]]      # readback reflects the write


def test_sheets_values_clear_records_and_clears_fixture():
    b = be()
    b.sheets_values_update("f", "Sheet1!A1", [["x"]])
    b.sheets_values_clear("f", "Sheet1!A1")
    assert b.get_values("f", "Sheet1!A1") == []


def test_slides_batch_update_records():
    b = be()
    b.slides_batch_update("f", [{"replaceAllText": {}}])
    assert ("f", "slides", [{"replaceAllText": {}}]) in b._writes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_backend_write.py -v`
Expected: FAIL — `AttributeError: 'FakeBackend' object has no attribute 'docs_batch_update'`.

- [ ] **Step 3: Extend the `Backend` protocol** — add to the `Backend` Protocol class in `backend.py`:

```python
    def docs_batch_update(self, file_id: str, requests: list) -> dict: ...
    def sheets_values_update(self, file_id: str, a1_range: str, values: list) -> dict: ...
    def sheets_values_clear(self, file_id: str, a1_range: str) -> dict: ...
    def sheets_batch_update(self, file_id: str, requests: list) -> dict: ...
    def slides_batch_update(self, file_id: str, requests: list) -> dict: ...
```

- [ ] **Step 4: Implement in `FakeBackend`** — add `self._writes = []` to `__init__`, then:

```python
    def docs_batch_update(self, file_id, requests):
        self._writes.append((file_id, "docs", requests)); return {}

    def sheets_values_update(self, file_id, a1_range, values):
        self._writes.append((file_id, "sheets_values_update", a1_range, values))
        self._values[(file_id, a1_range)] = values
        return {}

    def sheets_values_clear(self, file_id, a1_range):
        self._writes.append((file_id, "sheets_values_clear", a1_range))
        self._values.pop((file_id, a1_range), None)
        return {}

    def sheets_batch_update(self, file_id, requests):
        self._writes.append((file_id, "sheets", requests)); return {}

    def slides_batch_update(self, file_id, requests):
        self._writes.append((file_id, "slides", requests)); return {}
```

- [ ] **Step 5: Implement in `ApiBackend`**:

```python
    def docs_batch_update(self, file_id, requests):
        return _errors.call(self._services.docs.documents().batchUpdate(
            documentId=file_id, body={"requests": requests}).execute)

    def sheets_values_update(self, file_id, a1_range, values):
        return _errors.call(self._services.sheets.spreadsheets().values().update(
            spreadsheetId=file_id, range=a1_range, valueInputOption="RAW",
            body={"values": values}).execute)

    def sheets_values_clear(self, file_id, a1_range):
        return _errors.call(self._services.sheets.spreadsheets().values().clear(
            spreadsheetId=file_id, range=a1_range, body={}).execute)

    def sheets_batch_update(self, file_id, requests):
        return _errors.call(self._services.sheets.spreadsheets().batchUpdate(
            spreadsheetId=file_id, body={"requests": requests}).execute)

    def slides_batch_update(self, file_id, requests):
        return _errors.call(self._services.slides.presentations().batchUpdate(
            presentationId=file_id, body={"requests": requests}).execute)
```

- [ ] **Step 6: Add `_require_writable`** — in `base.py`, add to `Document`:

```python
    def _require_writable(self) -> None:
        if self.read_only:
            from . import exceptions as exc
            raise exc.ReadOnlyError("workspace is read_only; content writes are disabled")
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_backend_write.py -v`
Expected: PASS (4 tests). Then `pytest -q` (existing FakeBackend callers unaffected — `_writes` is a new attr).

- [ ] **Step 8: Commit**

```bash
git add src/csa_google_workspace/backend.py src/csa_google_workspace/base.py tests/test_backend_write.py
git commit -m "feat: content-write backend methods + Document._require_writable"
```

---

### Task 2: `Doc` writes

**Files:**
- Modify: `src/csa_google_workspace/documents/doc.py`
- Test: `tests/test_doc_write.py`

**Interfaces:**
- Consumes: `backend.docs_batch_update`, `backend.get_document` (for `append_text` end-index), `_require_writable`.
- Produces (all `read_only`-gated):
  - `Doc.replace_text(find: str, replace: str) -> None`
  - `Doc.insert_text(text: str, at: int) -> None`
  - `Doc.append_text(text: str) -> None`
  - `Doc.delete_range(start: int, end: int) -> None`
  - `Doc.batch_update(requests: list) -> dict` (raw escape hatch)

- [ ] **Step 1: Write the failing test** — `tests/test_doc_write.py`

```python
import pytest
from csa_google_workspace import Workspace, exceptions as exc
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
META = {"d": {"id": "d", "name": "D", "mimeType": DOC, "webViewLink": "https://x/document/d/d/edit"}}


def doc(read_only=False, document=None):
    b = FakeBackend(META, documents={"d": document or {"body": {"content": [{"endIndex": 10}]}}})
    return Workspace(b, read_only=read_only).open("d"), b


def test_replace_text_builds_replaceAllText():
    d, b = doc()
    d.replace_text("old", "new")
    assert b._writes == [("d", "docs", [{"replaceAllText": {
        "containsText": {"text": "old", "matchCase": True}, "replaceText": "new"}}])]


def test_insert_text_builds_insertText_at_index():
    d, b = doc()
    d.insert_text("hi", at=5)
    assert b._writes == [("d", "docs", [{"insertText": {"location": {"index": 5}, "text": "hi"}}])]


def test_append_text_inserts_before_final_newline():
    d, b = doc(document={"body": {"content": [{"endIndex": 42}]}})
    d.append_text("tail")
    assert b._writes == [("d", "docs", [{"insertText": {"location": {"index": 41}, "text": "tail"}}])]


def test_delete_range_builds_deleteContentRange():
    d, b = doc()
    d.delete_range(3, 7)
    assert b._writes == [("d", "docs", [{"deleteContentRange": {"range": {"startIndex": 3, "endIndex": 7}}}])]


def test_writes_blocked_when_read_only():
    d, _ = doc(read_only=True)
    for call in (lambda: d.replace_text("a", "b"), lambda: d.insert_text("x", 1),
                 lambda: d.append_text("x"), lambda: d.delete_range(1, 2),
                 lambda: d.batch_update([{}])):
        with pytest.raises(exc.ReadOnlyError):
            call()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_doc_write.py -v`
Expected: FAIL — `AttributeError: 'Doc' object has no attribute 'replace_text'`.

- [ ] **Step 3: Implement** — add to `Doc` in `documents/doc.py` (keep existing `as_text`/`paragraphs`):

```python
    def replace_text(self, find: str, replace: str) -> None:
        self._require_writable()
        self._backend.docs_batch_update(self.id, [{"replaceAllText": {
            "containsText": {"text": find, "matchCase": True}, "replaceText": replace}}])

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_doc_write.py -v`
Expected: PASS (5 tests). Then `pytest -q`.

- [ ] **Step 5: Commit**

```bash
git add src/csa_google_workspace/documents/doc.py tests/test_doc_write.py
git commit -m "feat: Doc content writes (replace/insert/append/delete/batch_update)"
```

---

### Task 3: `Sheet` writes

**Files:**
- Modify: `src/csa_google_workspace/documents/sheet.py`
- Test: `tests/test_sheet_write.py`

**Interfaces:**
- Consumes: `backend.sheets_values_update`/`sheets_values_clear`/`sheets_batch_update`, `_require_writable`.
- Produces (all `read_only`-gated): `Sheet.update(a1_range, values) -> None`, `Sheet.clear(a1_range) -> None`, `Sheet.batch_update(requests) -> dict`.

- [ ] **Step 1: Write the failing test** — `tests/test_sheet_write.py`

```python
import pytest
from csa_google_workspace import Workspace, exceptions as exc
from csa_google_workspace.backend import FakeBackend

SHEET = "application/vnd.google-apps.spreadsheet"
META = {"s": {"id": "s", "name": "S", "mimeType": SHEET, "webViewLink": "https://x/spreadsheets/d/s/edit"}}


def sheet(read_only=False):
    b = FakeBackend(META)
    return Workspace(b, read_only=read_only).open("s"), b


def test_update_writes_values_and_reads_back():
    s, b = sheet()
    s.update("Sheet1!A1", [["a", "b"]])
    assert ("s", "sheets_values_update", "Sheet1!A1", [["a", "b"]]) in b._writes
    assert s.values("Sheet1!A1") == [["a", "b"]]


def test_clear_records():
    s, b = sheet()
    s.update("Sheet1!A1", [["x"]]); s.clear("Sheet1!A1")
    assert ("s", "sheets_values_clear", "Sheet1!A1") in b._writes
    assert s.values("Sheet1!A1") == []


def test_batch_update_records():
    s, b = sheet()
    s.batch_update([{"repeatCell": {}}])
    assert ("s", "sheets", [{"repeatCell": {}}]) in b._writes


def test_writes_blocked_when_read_only():
    s, _ = sheet(read_only=True)
    for call in (lambda: s.update("A1", [["x"]]), lambda: s.clear("A1"), lambda: s.batch_update([{}])):
        with pytest.raises(exc.ReadOnlyError):
            call()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sheet_write.py -v`
Expected: FAIL — `AttributeError: 'Sheet' object has no attribute 'update'`.

- [ ] **Step 3: Implement** — add to `Sheet` (keep existing read + cell-map methods):

```python
    def update(self, a1_range: str, values: list) -> None:
        self._require_writable()
        self._backend.sheets_values_update(self.id, a1_range, values)

    def clear(self, a1_range: str) -> None:
        self._require_writable()
        self._backend.sheets_values_clear(self.id, a1_range)

    def batch_update(self, requests: list) -> dict:
        self._require_writable()
        return self._backend.sheets_batch_update(self.id, requests)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sheet_write.py -v`
Expected: PASS (4 tests). Then `pytest -q`.

- [ ] **Step 5: Commit**

```bash
git add src/csa_google_workspace/documents/sheet.py tests/test_sheet_write.py
git commit -m "feat: Sheet content writes (update/clear/batch_update)"
```

---

### Task 4: `Slides` writes

**Files:**
- Modify: `src/csa_google_workspace/documents/slides.py`
- Test: `tests/test_slides_write.py`

**Interfaces:**
- Consumes: `backend.slides_batch_update`, `_require_writable`.
- Produces (all `read_only`-gated): `Slides.replace_text(find, replace) -> None` (deck-wide), `Slides.batch_update(requests) -> dict`.

- [ ] **Step 1: Write the failing test** — `tests/test_slides_write.py`

```python
import pytest
from csa_google_workspace import Workspace, exceptions as exc
from csa_google_workspace.backend import FakeBackend

PRES = "application/vnd.google-apps.presentation"
META = {"p": {"id": "p", "name": "P", "mimeType": PRES, "webViewLink": "https://x/presentation/d/p/edit"}}


def slides(read_only=False):
    b = FakeBackend(META)
    return Workspace(b, read_only=read_only).open("p"), b


def test_replace_text_builds_deckwide_replaceAllText():
    p, b = slides()
    p.replace_text("old", "new")
    assert b._writes == [("p", "slides", [{"replaceAllText": {
        "containsText": {"text": "old", "matchCase": True}, "replaceText": "new"}}])]


def test_batch_update_records():
    p, b = slides()
    p.batch_update([{"createShape": {}}])
    assert ("p", "slides", [{"createShape": {}}]) in b._writes


def test_writes_blocked_when_read_only():
    p, _ = slides(read_only=True)
    for call in (lambda: p.replace_text("a", "b"), lambda: p.batch_update([{}])):
        with pytest.raises(exc.ReadOnlyError):
            call()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_slides_write.py -v`
Expected: FAIL — `AttributeError: 'Slides' object has no attribute 'replace_text'`.

- [ ] **Step 3: Implement** — add to `Slides` (keep existing `slides`/`as_text`):

```python
    def replace_text(self, find: str, replace: str) -> None:
        self._require_writable()
        self._backend.slides_batch_update(self.id, [{"replaceAllText": {
            "containsText": {"text": find, "matchCase": True}, "replaceText": replace}}])

    def batch_update(self, requests: list) -> dict:
        self._require_writable()
        return self._backend.slides_batch_update(self.id, requests)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_slides_write.py -v`
Expected: PASS (3 tests). Then `pytest -q`.

- [ ] **Step 5: Commit**

```bash
git add src/csa_google_workspace/documents/slides.py tests/test_slides_write.py
git commit -m "feat: Slides content writes (deck-wide replace_text + batch_update)"
```

---

### Task 5: Gated live content-write integration

**Files:**
- Modify: `tests/integration/test_all_types_live.py`

**Interfaces:**
- Consumes: the real write path.
- Produces: a gated test that writes to a throwaway Doc + Sheet and reads the change back through the library, then trashes them. Reuses the existing `_ws()` / `_throwaway()` helpers.

- [ ] **Step 1: Append the gated test** — to `tests/integration/test_all_types_live.py`

```python
def test_content_write_live():
    from csa_google_workspace import Doc, Sheet
    ws = _ws()
    with _throwaway(ws, "application/vnd.google-apps.document", "E2E-DocWrite-THROWAWAY") as fid:
        d = ws.open(fid)
        d.append_text("written by the library")
        assert "written by the library" in ws.open(fid).as_text()
        d.replace_text("written by the library", "edited by the library")
        assert "edited by the library" in ws.open(fid).as_text()
    with _throwaway(ws, "application/vnd.google-apps.spreadsheet", "E2E-SheetWrite-THROWAWAY") as sid:
        s = ws.open(sid)
        s.update("Sheet1!A1", [["hello", "world"]])
        assert s.values("Sheet1!A1:B1") == [["hello", "world"]]
        s.clear("Sheet1!A1:B1")
        assert s.values("Sheet1!A1:B1") == []
```

- [ ] **Step 2: Verify it SKIPS cleanly without credentials**

Run: `pytest tests/integration/ -v`
Expected: 6 skipped. Then `pytest -q` — full unit suite green + 6 skipped.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_all_types_live.py
git commit -m "test: gated live content-write (Doc append/replace, Sheet update/clear)"
```

---

## Notes for later phases (not this plan)
- **Docs suggestions read** (`doc.suggestions`, `doc.as_text(suggestions="accepted"|"rejected")`) — the last feature phase.
- Slides per-shape/positional text insertion (needs object-ID targeting; spec §14.3) — deferred beyond deck-wide `replace_text`.
- Multi-request index-safe batch helpers for Docs (back-to-front) — only if a future helper builds multi-edit batches; today's helpers are single-request.
- Real write call shapes exercised by Task 5's gated suite, not unit tests.

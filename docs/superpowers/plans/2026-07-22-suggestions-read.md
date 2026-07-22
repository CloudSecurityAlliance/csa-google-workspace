# csa-google-workspace — Phase 6 (Docs Suggestions Read) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read Google Docs **suggestions** (tracked "Suggesting mode" edits) — enumerate them and preview the doc as-if-accepted / as-if-rejected. **Read-only:** the Docs API has no accept/reject endpoint (proven), so none is offered.

**Architecture:** Extend `backend.get_document` with an optional `suggestions_view_mode`. A pure `suggestions.py` walks a `documents.get` response and groups suggested text-runs by id into `Suggestion`s. `Doc.suggestions` lists them; `Doc.as_text(suggestions="accepted"|"rejected"|"inline")` returns the previewed text via the three view-modes.

**Tech Stack:** Python 3.10+, `pytest`. Builds on Phases 1–5 (merged).

Spec §7. Empirical basis: [`experiments/docs-suggestions/RESULTS.md`](../../../experiments/docs-suggestions/RESULTS.md) and [`research/docs-suggestions-reference.md`](../../../research/docs-suggestions-reference.md).

## Global Constraints

- **Import name** `csa_google_workspace`; **`src/` layout**; **Python `>=3.10`**.
- **Read-only feature.** No accept/reject (no API exists). No `Suggestion.author` (the Docs API exposes none — measured).
- **Measured facts the extractor MUST honor** (from `experiments/docs-suggestions/`):
  - Suggested text lives on text runs via `suggestedInsertionIds` / `suggestedDeletionIds` (lists of ids).
  - **One logical suggestion spans multiple runs** sharing an id → **group by id**, preserving order, concatenating text.
  - View-modes: `SUGGESTIONS_INLINE` (with suggestions), `PREVIEW_SUGGESTIONS_ACCEPTED` (as accepted), `PREVIEW_WITHOUT_SUGGESTIONS` (as rejected).
- **Unit tests use `FakeBackend`** with document fixtures (per view-mode) — no network. Real path is integration-only, and since suggestions can only be created in the UI, the live test reads a **caller-provided** doc (env var), skipping if absent.

---

### Task 1: `Suggestion` model + extractor + `get_document` view-mode

**Files:**
- Create: `src/csa_google_workspace/suggestions.py`
- Modify: `src/csa_google_workspace/backend.py` (`get_document` gains `suggestions_view_mode`)
- Test: `tests/test_suggestions.py`

**Interfaces:**
- Consumes: nothing (extractor is pure).
- Produces:
  - `Suggestion(suggestion_id: str, kind: Literal["insertion","deletion"], text: str)` — **no author**.
  - `suggestions.extract_suggestions(document: dict) -> list[Suggestion]` (grouped by id, order-preserving).
  - `Backend.get_document(file_id, suggestions_view_mode: str | None = None) -> dict`; `ApiBackend` passes `suggestionsViewMode` when given; `FakeBackend` looks up `(file_id, mode)` then falls back to `file_id` (so existing single-arg callers/fixtures still work).

- [ ] **Step 1: Write the failing test** — `tests/test_suggestions.py`

```python
from csa_google_workspace.suggestions import Suggestion, extract_suggestions
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
META = {"d": {"id": "d", "name": "D", "mimeType": DOC, "webViewLink": "https://x/document/d/d/edit"}}


def _run(text, ins=None, dele=None):
    tr = {"textRun": {"content": text}}
    if ins:
        tr["textRun"]["suggestedInsertionIds"] = ins
    if dele:
        tr["textRun"]["suggestedDeletionIds"] = dele
    return tr


def _doc(*runs):
    return {"body": {"content": [{"paragraph": {"elements": list(runs)}}]}}


def test_insertion_spanning_multiple_runs_is_one_suggestion():
    doc = _doc(_run("Hello ", ins=["s1"]), _run("world", ins=["s1"]), _run(" plain"))
    sugg = extract_suggestions(doc)
    assert len(sugg) == 1
    assert sugg[0].suggestion_id == "s1" and sugg[0].kind == "insertion" and sugg[0].text == "Hello world"


def test_deletion_detected():
    sugg = extract_suggestions(_doc(_run("remove me", dele=["s2"])))
    assert sugg[0].kind == "deletion" and sugg[0].text == "remove me"


def test_no_author_field():
    assert not hasattr(extract_suggestions(_doc(_run("x", ins=["s1"])))[0], "author")


def test_get_document_view_mode_fixture_lookup():
    b = FakeBackend(META, documents={("d", "PREVIEW_SUGGESTIONS_ACCEPTED"): {"body": {"content": []}, "title": "accepted"}})
    assert b.get_document("d", "PREVIEW_SUGGESTIONS_ACCEPTED")["title"] == "accepted"


def test_get_document_falls_back_to_plain_key():
    b = FakeBackend(META, documents={"d": {"title": "plain"}})
    assert b.get_document("d")["title"] == "plain"                    # existing single-arg behavior intact
    assert b.get_document("d", "SUGGESTIONS_INLINE")["title"] == "plain"  # falls back to plain key
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_suggestions.py -v`
Expected: FAIL — `ModuleNotFoundError: csa_google_workspace.suggestions` / `get_document` takes 1 arg.

- [ ] **Step 3: Write** — `src/csa_google_workspace/suggestions.py`

```python
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
```

- [ ] **Step 4: Extend `get_document`.** In `backend.py`:
  - Protocol: `def get_document(self, file_id: str, suggestions_view_mode: str | None = None) -> dict: ...`
  - `FakeBackend.get_document`:
    ```python
    def get_document(self, file_id, suggestions_view_mode=None):
        key = (file_id, suggestions_view_mode)
        if key in self._documents:
            import copy
            return copy.deepcopy(self._documents[key])
        return self._fixture(self._documents, file_id, "document")
    ```
  - `ApiBackend.get_document`:
    ```python
    def get_document(self, file_id, suggestions_view_mode=None):
        kw = {"documentId": file_id}
        if suggestions_view_mode:
            kw["suggestionsViewMode"] = suggestions_view_mode
        return _errors.call(self._services.docs.documents().get(**kw).execute)
    ```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_suggestions.py -v`
Expected: PASS (5 tests). Then `pytest -q` (existing `get_document` callers unaffected — new param defaults to None).

- [ ] **Step 6: Commit**

```bash
git add src/csa_google_workspace/suggestions.py src/csa_google_workspace/backend.py tests/test_suggestions.py
git commit -m "feat: Suggestion model + extractor + get_document view-mode param"
```

---

### Task 2: `Doc.suggestions` + `Doc.as_text(suggestions=...)`

**Files:**
- Modify: `src/csa_google_workspace/documents/doc.py`
- Test: `tests/test_doc_suggestions.py`

**Interfaces:**
- Consumes: `suggestions.extract_suggestions`, `backend.get_document(..., mode)`, `_content.doc_text`.
- Produces:
  - `Doc.suggestions -> list[Suggestion]` (from `SUGGESTIONS_INLINE`).
  - `Doc.as_text(suggestions: str | None = None) -> str` — `None`→default; `"inline"`→`SUGGESTIONS_INLINE`; `"accepted"`→`PREVIEW_SUGGESTIONS_ACCEPTED`; `"rejected"`→`PREVIEW_WITHOUT_SUGGESTIONS`. (Overrides the base `as_text`.)

- [ ] **Step 1: Write the failing test** — `tests/test_doc_suggestions.py`

```python
from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
META = {"d": {"id": "d", "name": "D", "mimeType": DOC, "webViewLink": "https://x/document/d/d/edit"}}


def _run(text, ins=None):
    tr = {"textRun": {"content": text}}
    if ins:
        tr["textRun"]["suggestedInsertionIds"] = ins
    return tr


def _para(*runs):
    return {"paragraph": {"elements": list(runs)}}


def _doc_with_modes():
    inline = {"body": {"content": [_para(_run("Base "), _run("added", ins=["s1"]))]}}
    accepted = {"body": {"content": [_para(_run("Base added"))]}}
    rejected = {"body": {"content": [_para(_run("Base "))]}}
    return FakeBackend(META, documents={
        ("d", "SUGGESTIONS_INLINE"): inline,
        ("d", "PREVIEW_SUGGESTIONS_ACCEPTED"): accepted,
        ("d", "PREVIEW_WITHOUT_SUGGESTIONS"): rejected,
        "d": inline,
    })


def test_suggestions_lists_grouped():
    d = Workspace(_doc_with_modes()).open("d")
    s = d.suggestions
    assert len(s) == 1 and s[0].kind == "insertion" and s[0].text == "added"


def test_as_text_accepted_and_rejected_previews():
    d = Workspace(_doc_with_modes()).open("d")
    assert d.as_text(suggestions="accepted") == "Base added"
    assert d.as_text(suggestions="rejected") == "Base "


def test_as_text_default_still_works():
    d = Workspace(_doc_with_modes()).open("d")
    assert "Base" in d.as_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_doc_suggestions.py -v`
Expected: FAIL — `AttributeError: 'Doc' object has no attribute 'suggestions'`.

- [ ] **Step 3: Implement** — in `documents/doc.py`, add `suggestions` and replace `as_text`:

```python
from .. import _content, suggestions as _suggestions

_VIEW = {"inline": "SUGGESTIONS_INLINE", "accepted": "PREVIEW_SUGGESTIONS_ACCEPTED",
         "rejected": "PREVIEW_WITHOUT_SUGGESTIONS"}


class Doc(Document):
    # ... keep paragraphs + all write methods ...

    def as_text(self, suggestions: str | None = None) -> str:
        mode = _VIEW[suggestions] if suggestions else None
        return _content.doc_text(self._backend.get_document(self.id, mode))

    @property
    def suggestions(self) -> list:
        doc = self._backend.get_document(self.id, "SUGGESTIONS_INLINE")
        return _suggestions.extract_suggestions(doc)
```
(Keep the existing `paragraphs` property and every write method; only `as_text` changes signature, and `suggestions` is new. Update the module imports at the top of `doc.py` to include `suggestions as _suggestions`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_doc_suggestions.py -v`
Expected: PASS (3 tests). Then `pytest -q` (the `as_text()` no-arg call still works — `suggestions` defaults to `None`).

- [ ] **Step 5: Commit**

```bash
git add src/csa_google_workspace/documents/doc.py tests/test_doc_suggestions.py
git commit -m "feat: Doc.suggestions + as_text(suggestions=accepted|rejected|inline)"
```

---

### Task 3: Gated live suggestions test

**Files:**
- Modify: `tests/integration/test_all_types_live.py`

**Interfaces:**
- Consumes: `Doc.suggestions` + `as_text` against a real doc that already has suggestions.
- Produces: a gated test, **also skipped unless `CSA_GW_SUGGESTIONS_DOC` is set** (a doc id with suggesting-mode edits — since suggestions can't be created via the API), that reads its suggestions and asserts accepted/rejected previews differ.

- [ ] **Step 1: Append the gated test** — to `tests/integration/test_all_types_live.py`

```python
def test_suggestions_read_live():
    doc_id = os.environ.get("CSA_GW_SUGGESTIONS_DOC")
    if not doc_id:
        pytest.skip("set CSA_GW_SUGGESTIONS_DOC to a Doc id that has suggesting-mode edits")
    from csa_google_workspace import Doc
    ws = _ws()
    d = ws.open(doc_id)
    assert isinstance(d, Doc)
    sugg = d.suggestions
    assert isinstance(sugg, list) and all(s.kind in ("insertion", "deletion") for s in sugg)
    # accepted vs rejected previews should differ when suggestions exist
    if sugg:
        assert d.as_text(suggestions="accepted") != d.as_text(suggestions="rejected")
```
(`os` and `pytest` are already imported at the top of the file.)

- [ ] **Step 2: Verify it SKIPS cleanly**

Run: `pytest tests/integration/ -v`
Expected: 6 skipped (this one skips on either `CSA_GW_INTEGRATION` or `CSA_GW_SUGGESTIONS_DOC`). Then `pytest -q` — full unit suite green + 6 skipped.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_all_types_live.py
git commit -m "test: gated live Docs suggestions read"
```

---

## Notes for later phases (not this plan)
- This is the **last feature phase**. Remaining work is the tracked Tier-C polish (per the project ledger): `replace_text` returning `occurrencesChanged`, cell-map cache-on-write invalidation, `Location.tab` resolution, `SERVICE_DISABLED` message parsing, `RateLimitError.retry_after`, etc.
- Accept/reject of suggestions remains impossible via the API — a future `PlaywrightBackend` concern (spec §13).
- Real suggestions path exercised by Task 3's env-gated live test, not unit tests.

# csa-google-workspace — Phase 1 (Foundations) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundation of the `csa-google-workspace` library — authenticate, open a Drive file, get back the correct typed `Document` subclass, with a testable `Backend` seam and a typed error hierarchy — so later phases (comments, content, suggestions) have a base to build on.

**Architecture:** A `Workspace` factory sniffs a file's MIME type and returns a `Doc`/`Sheet`/`Slides` object. All Google API access goes through a `Backend` protocol; v1 ships `ApiBackend` (real `google-api-python-client`) and `FakeBackend` (in-memory, for tests). Operations the API cannot do raise `UnsupportedOperation`.

**Tech Stack:** Python 3.10+, `google-api-python-client`, `google-auth`, `google-auth-oauthlib`, `pytest`.

Spec: [`docs/superpowers/specs/2026-07-20-csa-google-workspace-design.md`](../specs/2026-07-20-csa-google-workspace-design.md).

## Global Constraints

- **Import name** `csa_google_workspace`; distribution name `csa-google-workspace`; **`src/` layout**.
- **Python** `>=3.10` (uses `X | None` syntax).
- **Dependencies:** `google-api-python-client`, `google-auth`, `google-auth-oauthlib`. Dev: `pytest`.
- **Writes ON by default:** `read_only=False` is the default everywhere.
- **Unit tests use `FakeBackend`** — no network, no credentials.
- **No persistent storage** of comment/file content.
- MIME map: `application/vnd.google-apps.document`→`Doc`, `…spreadsheet`→`Sheet`, `…presentation`→`Slides`.

---

### Task 1: Package scaffold + exception hierarchy

**Files:**
- Create: `pyproject.toml`
- Create: `src/csa_google_workspace/__init__.py`
- Create: `src/csa_google_workspace/exceptions.py`
- Test: `tests/test_exceptions.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `CsaWorkspaceError` (base) and subclasses `AuthError`, `ServiceDisabledError(service, activation_url)`, `ReadOnlyError`, `NotFoundError`, `AccessError`, `RateLimitError(retry_after)`, `UnsupportedOperation`, `ApiError(status, reason, message)`.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "csa-google-workspace"
version = "0.0.1"
description = "Read/write content and manage comments on Google Docs, Sheets, and Slides"
requires-python = ">=3.10"
dependencies = [
    "google-api-python-client>=2.0",
    "google-auth>=2.0",
    "google-auth-oauthlib>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: Write the failing test** — `tests/test_exceptions.py`

```python
import pytest
from csa_google_workspace import exceptions as exc


def test_all_errors_subclass_base():
    for cls in (exc.AuthError, exc.ServiceDisabledError, exc.ReadOnlyError,
                exc.NotFoundError, exc.AccessError, exc.RateLimitError,
                exc.UnsupportedOperation, exc.ApiError):
        assert issubclass(cls, exc.CsaWorkspaceError)


def test_service_disabled_carries_service_and_url():
    e = exc.ServiceDisabledError("docs.googleapis.com", "https://console/enable")
    assert e.service == "docs.googleapis.com"
    assert "console" in e.activation_url
    assert "docs.googleapis.com" in str(e)


def test_api_error_carries_status_reason():
    e = exc.ApiError(status=404, reason="notFound", message="missing")
    assert e.status == 404 and e.reason == "notFound"


def test_rate_limit_carries_retry_after():
    assert exc.RateLimitError(retry_after=30).retry_after == 30
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pip install -e ".[dev]" && pytest tests/test_exceptions.py -v`
Expected: FAIL — `ModuleNotFoundError`/`AttributeError` (exceptions not defined).

- [ ] **Step 4: Write minimal implementation** — `src/csa_google_workspace/exceptions.py`

```python
"""Typed error hierarchy. Callers never touch raw googleapiclient HttpError."""


class CsaWorkspaceError(Exception):
    """Base for every library error."""


class AuthError(CsaWorkspaceError):
    """Bad/expired credentials, or consent needed."""


class ServiceDisabledError(CsaWorkspaceError):
    """A Google API is not enabled in the Cloud project (403 SERVICE_DISABLED)."""

    def __init__(self, service: str, activation_url: str):
        self.service = service
        self.activation_url = activation_url
        super().__init__(
            f"The API '{service}' is not enabled for this Google Cloud project. "
            f"Enable it at {activation_url} and retry (allow a few minutes to propagate)."
        )


class ReadOnlyError(CsaWorkspaceError):
    """A mutating call was made while the workspace is read_only=True."""


class NotFoundError(CsaWorkspaceError):
    """A file, comment, or reply id does not exist (404)."""


class AccessError(CsaWorkspaceError):
    """Insufficient permission (403) — not shared, wrong scope, or editing another's comment."""


class RateLimitError(CsaWorkspaceError):
    """Rate limit hit (429). `retry_after` is seconds, if the server provided it."""

    def __init__(self, retry_after: int | None = None):
        self.retry_after = retry_after
        super().__init__(f"Rate limited; retry after {retry_after}s" if retry_after else "Rate limited")


class UnsupportedOperation(CsaWorkspaceError):
    """The operation is impossible on this backend (e.g. accept a suggestion via the API)."""


class ApiError(CsaWorkspaceError):
    """Catch-all wrapper for an unclassified googleapiclient HttpError."""

    def __init__(self, status: int, reason: str, message: str):
        self.status = status
        self.reason = reason
        super().__init__(f"[{status} {reason}] {message}")
```

- [ ] **Step 5: Create the package export** — `src/csa_google_workspace/__init__.py`

```python
from . import exceptions  # noqa: F401

__all__ = ["exceptions"]
__version__ = "0.0.1"
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_exceptions.py -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/csa_google_workspace/__init__.py src/csa_google_workspace/exceptions.py tests/test_exceptions.py
git commit -m "feat: package scaffold + typed exception hierarchy"
```

---

### Task 2: Backend protocol + FakeBackend + ApiBackend skeleton

**Files:**
- Create: `src/csa_google_workspace/backend.py`
- Test: `tests/test_backend.py`

**Interfaces:**
- Consumes: `exceptions.UnsupportedOperation`.
- Produces:
  - `Backend` protocol: `get_file_metadata(file_id: str) -> dict` (keys `id,name,mimeType,webViewLink`); `accept_suggestion(file_id, suggestion_id) -> None`; `create_cell_anchored_comment(file_id, cell, text) -> None`.
  - `FakeBackend(files: dict[str, dict])` — in-memory; `get_file_metadata` returns `files[file_id]` or raises `NotFoundError`.
  - `ApiBackend(services)` — `accept_suggestion`/`create_cell_anchored_comment` raise `UnsupportedOperation`. (`services` is the Task 4 `ServiceRegistry`; typed loosely here.)

- [ ] **Step 1: Write the failing test** — `tests/test_backend.py`

```python
import pytest
from csa_google_workspace.backend import FakeBackend, ApiBackend
from csa_google_workspace import exceptions as exc

FILES = {"doc1": {"id": "doc1", "name": "D", "mimeType": "application/vnd.google-apps.document",
                  "webViewLink": "https://docs.google.com/document/d/doc1/edit"}}


def test_fake_backend_returns_metadata():
    assert FakeBackend(FILES).get_file_metadata("doc1")["mimeType"].endswith("document")


def test_fake_backend_missing_file_raises_not_found():
    with pytest.raises(exc.NotFoundError):
        FakeBackend(FILES).get_file_metadata("nope")


def test_api_backend_accept_suggestion_unsupported():
    with pytest.raises(exc.UnsupportedOperation):
        ApiBackend(services=None).accept_suggestion("doc1", "sug1")


def test_api_backend_cell_anchored_comment_unsupported():
    with pytest.raises(exc.UnsupportedOperation):
        ApiBackend(services=None).create_cell_anchored_comment("sheet1", "B11", "hi")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_backend.py -v`
Expected: FAIL — `ModuleNotFoundError: csa_google_workspace.backend`.

- [ ] **Step 3: Write minimal implementation** — `src/csa_google_workspace/backend.py`

```python
"""Backend seam. ApiBackend uses the real Google APIs; FakeBackend is in-memory for tests.
Operations Google exposes only through the UI raise UnsupportedOperation on ApiBackend; a
future PlaywrightBackend could implement them without changing the public API."""
from typing import Protocol

from . import exceptions as exc


class Backend(Protocol):
    def get_file_metadata(self, file_id: str) -> dict: ...
    def accept_suggestion(self, file_id: str, suggestion_id: str) -> None: ...
    def create_cell_anchored_comment(self, file_id: str, cell: str, text: str) -> None: ...


class FakeBackend:
    """In-memory backend for unit tests. `files` maps file_id -> metadata dict."""

    def __init__(self, files: dict[str, dict]):
        self._files = files

    def get_file_metadata(self, file_id: str) -> dict:
        try:
            return self._files[file_id]
        except KeyError:
            raise exc.NotFoundError(f"file '{file_id}' not found") from None

    def accept_suggestion(self, file_id: str, suggestion_id: str) -> None:
        raise exc.UnsupportedOperation("accept_suggestion is not supported by FakeBackend")

    def create_cell_anchored_comment(self, file_id: str, cell: str, text: str) -> None:
        raise exc.UnsupportedOperation("cell-anchored comments are not creatable")


class ApiBackend:
    """Real backend over google-api-python-client. `services` is a ServiceRegistry (Task 4)."""

    def __init__(self, services):
        self._services = services

    def get_file_metadata(self, file_id: str) -> dict:
        return (self._services.drive.files()
                .get(fileId=file_id, fields="id,name,mimeType,webViewLink")
                .execute())

    def accept_suggestion(self, file_id: str, suggestion_id: str) -> None:
        raise exc.UnsupportedOperation(
            "The Google Docs API has no accept/reject-suggestion endpoint "
            "(verified by probe). A PlaywrightBackend is required."
        )

    def create_cell_anchored_comment(self, file_id: str, cell: str, text: str) -> None:
        raise exc.UnsupportedOperation(
            "Cell-anchored comments cannot be created via the API; use a file-level "
            "comment with a #range deep-link instead."
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backend.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/csa_google_workspace/backend.py tests/test_backend.py
git commit -m "feat: Backend protocol + FakeBackend + ApiBackend skeleton"
```

---

### Task 3: Auth scope selection + re-consent detection

**Files:**
- Create: `src/csa_google_workspace/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure logic + a thin flow).
- Produces:
  - `scopes_for(read_only: bool) -> list[str]` — read/write vs `.readonly` scope sets.
  - `needs_reconsent(granted: list[str], required: list[str]) -> bool` — True if any required scope is missing.
  - `load_credentials(client_secrets: str, token_path: str, read_only: bool)` — returns a `google.oauth2.credentials.Credentials` (interactive first run; refresh/re-consent otherwise). *(Integration-tested only; unit tests cover the two pure functions.)*

- [ ] **Step 1: Write the failing test** — `tests/test_auth.py`

```python
from csa_google_workspace import auth


def test_scopes_readwrite_include_all_four_services():
    s = auth.scopes_for(read_only=False)
    assert any(x.endswith("/auth/drive") for x in s)
    assert any(x.endswith("/auth/documents") for x in s)
    assert any(x.endswith("/auth/spreadsheets") for x in s)
    assert any(x.endswith("/auth/presentations") for x in s)
    assert not any(".readonly" in x for x in s)


def test_scopes_readonly_are_all_readonly_variants():
    s = auth.scopes_for(read_only=True)
    assert all(x.endswith(".readonly") for x in s)
    assert len(s) == 4


def test_needs_reconsent_true_when_scope_missing():
    granted = ["https://www.googleapis.com/auth/drive.readonly"]
    required = auth.scopes_for(read_only=False)
    assert auth.needs_reconsent(granted, required) is True


def test_needs_reconsent_false_when_all_present():
    required = auth.scopes_for(read_only=False)
    assert auth.needs_reconsent(granted=required, required=required) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: csa_google_workspace.auth`.

- [ ] **Step 3: Write minimal implementation** — `src/csa_google_workspace/auth.py`

```python
"""OAuth installed-app flow + scope logic. Acts as a real user; writes on by default."""
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

_BASE = "https://www.googleapis.com/auth/"
_RW = [f"{_BASE}drive", f"{_BASE}documents", f"{_BASE}spreadsheets", f"{_BASE}presentations"]
_RO = [f"{s}.readonly" for s in _RW]


def scopes_for(read_only: bool) -> list[str]:
    return list(_RO if read_only else _RW)


def needs_reconsent(granted: list[str], required: list[str]) -> bool:
    return not set(required).issubset(set(granted or []))


def load_credentials(client_secrets: str, token_path: str, read_only: bool) -> Credentials:
    required = scopes_for(read_only)
    token_path = os.path.expanduser(token_path)
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path)
        if needs_reconsent(list(creds.scopes or []), required):
            creds = None  # cached token lacks the scopes we now need → re-consent
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        creds = InstalledAppFlow.from_client_secrets_file(client_secrets, required).run_local_server(port=0)
    os.makedirs(os.path.dirname(token_path) or ".", exist_ok=True)
    with open(token_path, "w") as f:
        f.write(creds.to_json())
    return creds
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_auth.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/csa_google_workspace/auth.py tests/test_auth.py
git commit -m "feat: OAuth scope selection + re-consent detection"
```

---

### Task 4: Lazy service registry

**Files:**
- Create: `src/csa_google_workspace/_services.py`
- Test: `tests/test_services.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `ServiceRegistry(credentials, builder=...)` with lazy properties `.drive`, `.docs`, `.sheets`, `.slides`. `builder(name, version, credentials)` defaults to `googleapiclient.discovery.build`; each service is built at most once, only on first access.

- [ ] **Step 1: Write the failing test** — `tests/test_services.py`

```python
from csa_google_workspace._services import ServiceRegistry


def test_lazy_build_only_on_access_and_cached():
    calls = []

    def fake_builder(name, version, credentials=None):
        calls.append((name, version))
        return f"{name}-{version}-client"

    reg = ServiceRegistry(credentials="creds", builder=fake_builder)
    assert calls == []                      # nothing built yet
    assert reg.drive == "drive-v3-client"   # builds on first access
    assert reg.drive == "drive-v3-client"   # cached
    assert calls == [("drive", "v3")]       # built exactly once
    assert reg.docs == "docs-v1-client"
    assert ("docs", "v1") in calls and len(calls) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_services.py -v`
Expected: FAIL — `ModuleNotFoundError: csa_google_workspace._services`.

- [ ] **Step 3: Write minimal implementation** — `src/csa_google_workspace/_services.py`

```python
"""Lazily builds the four Google API clients. Opening a Sheet never builds the Docs client."""
from googleapiclient.discovery import build as _default_build

_SPECS = {"drive": "v3", "docs": "v1", "sheets": "v4", "slides": "v1"}


class ServiceRegistry:
    def __init__(self, credentials, builder=_default_build):
        self._credentials = credentials
        self._builder = builder
        self._cache: dict[str, object] = {}

    def _get(self, name: str):
        if name not in self._cache:
            self._cache[name] = self._builder(name, _SPECS[name], credentials=self._credentials)
        return self._cache[name]

    @property
    def drive(self):
        return self._get("drive")

    @property
    def docs(self):
        return self._get("docs")

    @property
    def sheets(self):
        return self._get("sheets")

    @property
    def slides(self):
        return self._get("slides")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_services.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/csa_google_workspace/_services.py tests/test_services.py
git commit -m "feat: lazy Google API service registry"
```

---

### Task 5: Document base + Doc/Sheet/Slides shells

**Files:**
- Create: `src/csa_google_workspace/base.py`
- Create: `src/csa_google_workspace/documents/__init__.py`
- Create: `src/csa_google_workspace/documents/doc.py`
- Create: `src/csa_google_workspace/documents/sheet.py`
- Create: `src/csa_google_workspace/documents/slides.py`
- Test: `tests/test_document.py`

**Interfaces:**
- Consumes: `Backend` (Task 2).
- Produces:
  - `Document(backend, metadata: dict, read_only: bool)` with attributes `id, name, type, url, mime_type, read_only`. `type` is `"document"|"spreadsheet"|"presentation"`.
  - `Doc`, `Sheet`, `Slides` subclasses (shells for now).
  - `MIME_TO_TYPE: dict[str, str]` and `subclass_for_mime(mime: str) -> type[Document]`.

- [ ] **Step 1: Write the failing test** — `tests/test_document.py`

```python
import pytest
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.base import subclass_for_mime, Document
from csa_google_workspace.documents.doc import Doc
from csa_google_workspace.documents.sheet import Sheet
from csa_google_workspace.documents.slides import Slides
from csa_google_workspace import exceptions as exc

DOC_MIME = "application/vnd.google-apps.document"


def test_subclass_for_mime_maps_each_type():
    assert subclass_for_mime(DOC_MIME) is Doc
    assert subclass_for_mime("application/vnd.google-apps.spreadsheet") is Sheet
    assert subclass_for_mime("application/vnd.google-apps.presentation") is Slides


def test_subclass_for_mime_rejects_unknown():
    with pytest.raises(exc.UnsupportedOperation):
        subclass_for_mime("application/pdf")


def test_document_exposes_metadata():
    meta = {"id": "d1", "name": "My Doc", "mimeType": DOC_MIME,
            "webViewLink": "https://docs.google.com/document/d/d1/edit"}
    d = Doc(FakeBackend({}), meta, read_only=False)
    assert (d.id, d.name, d.type, d.read_only) == ("d1", "My Doc", "document", False)
    assert isinstance(d, Document)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_document.py -v`
Expected: FAIL — modules not found.

- [ ] **Step 3: Write `base.py`**

```python
"""Document base + MIME→subclass mapping. Subclasses live in documents/."""
from __future__ import annotations

from .backend import Backend
from . import exceptions as exc

MIME_TO_TYPE = {
    "application/vnd.google-apps.document": "document",
    "application/vnd.google-apps.spreadsheet": "spreadsheet",
    "application/vnd.google-apps.presentation": "presentation",
}


class Document:
    """Abstract base. Never instantiated directly — use Workspace.open()."""

    def __init__(self, backend: Backend, metadata: dict, read_only: bool):
        self._backend = backend
        self.id = metadata["id"]
        self.name = metadata.get("name", "")
        self.mime_type = metadata["mimeType"]
        self.type = MIME_TO_TYPE[self.mime_type]
        self.url = metadata.get("webViewLink", "")
        self.read_only = read_only

    def reload(self) -> None:
        """Drop cached state (none yet in Phase 1)."""


def subclass_for_mime(mime: str) -> type[Document]:
    if mime not in MIME_TO_TYPE:
        raise exc.UnsupportedOperation(f"unsupported file type: {mime}")
    from .documents.doc import Doc
    from .documents.sheet import Sheet
    from .documents.slides import Slides
    return {"document": Doc, "spreadsheet": Sheet, "presentation": Slides}[MIME_TO_TYPE[mime]]
```

- [ ] **Step 4: Write the three shells + package init**

`src/csa_google_workspace/documents/__init__.py` (intentionally near-empty — just marks the subpackage):
```python
"""Typed Document subclasses: Doc, Sheet, Slides."""
```

`src/csa_google_workspace/documents/doc.py`:
```python
from ..base import Document


class Doc(Document):
    """Google Docs. Content read/write + suggestions arrive in later phases."""
```

`src/csa_google_workspace/documents/sheet.py`:
```python
from ..base import Document


class Sheet(Document):
    """Google Sheets. Ranges + cell mapping arrive in later phases."""
```

`src/csa_google_workspace/documents/slides.py`:
```python
from ..base import Document


class Slides(Document):
    """Google Slides. Slide/text read/write arrives in later phases."""
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_document.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add src/csa_google_workspace/base.py src/csa_google_workspace/documents/ tests/test_document.py
git commit -m "feat: Document base + Doc/Sheet/Slides shells + MIME mapping"
```

---

### Task 6: Workspace factory (`open` / `open_by_url`)

**Files:**
- Create: `src/csa_google_workspace/workspace.py`
- Modify: `src/csa_google_workspace/__init__.py` (export `Workspace`, `Doc`, `Sheet`, `Slides`)
- Test: `tests/test_workspace.py`

**Interfaces:**
- Consumes: `Backend`/`FakeBackend` (Task 2), `subclass_for_mime` + `Document` (Task 5), `auth` (Task 3), `ServiceRegistry` + `ApiBackend` (Tasks 4/2).
- Produces:
  - `parse_file_id(url_or_id: str) -> str`.
  - `Workspace(backend: Backend, read_only: bool = False)` with `.open(file_id_or_url) -> Document` and `.open_by_url(url) -> Document`.
  - `Workspace.from_oauth(client_secrets, token_path=..., read_only=False) -> Workspace` (wires auth→services→ApiBackend; integration-tested).

- [ ] **Step 1: Write the failing test** — `tests/test_workspace.py`

```python
import pytest
from csa_google_workspace import Workspace, Doc, Sheet, Slides
from csa_google_workspace.workspace import parse_file_id
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"
FILES = {
    "d1": {"id": "d1", "name": "Doc", "mimeType": DOC, "webViewLink": "https://x/document/d/d1/edit"},
    "s1": {"id": "s1", "name": "Sheet", "mimeType": SHEET, "webViewLink": "https://x/spreadsheets/d/s1/edit"},
}


@pytest.mark.parametrize("value,expected", [
    ("d1", "d1"),
    ("https://docs.google.com/document/d/ABC123/edit?tab=t.0", "ABC123"),
    ("https://docs.google.com/spreadsheets/d/S-9_x/edit#gid=0", "S-9_x"),
    ("https://drive.google.com/file/d/FID/view", "FID"),
])
def test_parse_file_id(value, expected):
    assert parse_file_id(value) == expected


def test_open_returns_typed_subclass():
    ws = Workspace(FakeBackend(FILES))
    assert isinstance(ws.open("d1"), Doc)
    assert isinstance(ws.open("s1"), Sheet)


def test_open_by_url_extracts_id_then_opens():
    ws = Workspace(FakeBackend(FILES))
    d = ws.open_by_url("https://docs.google.com/document/d/d1/edit")
    assert isinstance(d, Doc) and d.id == "d1"


def test_read_only_propagates_to_document():
    ws = Workspace(FakeBackend(FILES), read_only=True)
    assert ws.open("d1").read_only is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_workspace.py -v`
Expected: FAIL — `ImportError: cannot import name 'Workspace'`.

- [ ] **Step 3: Write minimal implementation** — `src/csa_google_workspace/workspace.py`

```python
"""Entry point. Workspace.open() sniffs MIME type and returns the right typed Document."""
from __future__ import annotations

import re

from .backend import Backend, ApiBackend
from .base import Document, subclass_for_mime

_ID_IN_URL = re.compile(r"/d/([a-zA-Z0-9_-]+)")


def parse_file_id(url_or_id: str) -> str:
    m = _ID_IN_URL.search(url_or_id)
    return m.group(1) if m else url_or_id


class Workspace:
    def __init__(self, backend: Backend, read_only: bool = False):
        self._backend = backend
        self.read_only = read_only

    def open(self, file_id_or_url: str) -> Document:
        file_id = parse_file_id(file_id_or_url)
        meta = self._backend.get_file_metadata(file_id)
        cls = subclass_for_mime(meta["mimeType"])
        return cls(self._backend, meta, read_only=self.read_only)

    def open_by_url(self, url: str) -> Document:
        return self.open(url)

    @classmethod
    def from_oauth(cls, client_secrets: str,
                   token_path: str = "~/.csa_google_workspace/token.json",
                   read_only: bool = False) -> "Workspace":
        from .auth import load_credentials
        from ._services import ServiceRegistry
        creds = load_credentials(client_secrets, token_path, read_only)
        return cls(ApiBackend(ServiceRegistry(creds)), read_only=read_only)
```

- [ ] **Step 4: Update `__init__.py` exports**

```python
from . import exceptions  # noqa: F401
from .workspace import Workspace
from .documents.doc import Doc
from .documents.sheet import Sheet
from .documents.slides import Slides

__all__ = ["Workspace", "Doc", "Sheet", "Slides", "exceptions"]
__version__ = "0.0.1"
```

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: PASS (all tasks' tests green).

- [ ] **Step 6: Commit**

```bash
git add src/csa_google_workspace/workspace.py src/csa_google_workspace/__init__.py tests/test_workspace.py
git commit -m "feat: Workspace factory — open/open_by_url returns typed Document"
```

---

## Notes for later phases (not this plan)
- **Phase 2 (comments)** extends `Backend` with comment/reply methods and adds `CommentsMixin` to `Document`, plus `Comment`/`Reply`/`Author`/`CommentCollection` (spec §5). `FakeBackend` gains an in-memory comment store seeded from sanitized probe fixtures.
- `from_oauth` and `ApiBackend`'s real Google calls are covered by the **live integration suite** (spec §11), gated behind an env var — not the unit tests above.
- `ApiBackend.get_file_metadata` error mapping (404→`NotFoundError`, 403 `SERVICE_DISABLED`→`ServiceDisabledError`, etc.) lands with Phase 2's shared `HttpError`→typed-exception translator, since that's where it's first exercised over the wire.

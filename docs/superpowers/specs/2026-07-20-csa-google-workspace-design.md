# `csa-google-workspace` — Design Spec

> **Status:** design, approved for planning · **Date:** 2026-07-20
> A Python library for reading/writing **content** and managing **comments** on
> Google **Docs, Sheets, and Slides**. Distribution name `csa-google-workspace`;
> import name `csa_google_workspace`.
>
> Every behavioral claim here is grounded either in the research under
> [`research/`](../../../research/) or in a live probe under
> [`experiments/`](../../../experiments/). Where the two disagreed, the probe won.

---

## 1. Purpose & scope

A document-centric library for the workflow: **open a document → read its content and
comments → reply/resolve comments → optionally edit content → surface suggestions.**
It is the missing *domain* layer over Google's APIs — the raw `google-api-python-client`
handles auth and transport; this library adds the comment thread model, resolve/delete
semantics, Sheets cell-mapping, suggestion reading, and a uniform door across three file types.

### In scope
- **Comments** (Drive API v3): list/read, create, reply, resolve/reopen, edit, soft-delete —
  uniform across all three file types.
- **Content read** (Docs/Sheets/Slides APIs): plain text + structured access; Drive export.
- **Content write** (Docs/Sheets/Slides APIs): high-level helpers (`replace_text`, `append_text`,
  cell `update`) plus a raw `batch_update` escape hatch per type.
- **Suggestions (Docs)**: **read-only** — enumerate suggested edits; accepted/rejected text previews.
- **Sheets cell mapping**: best-effort comment → A1 via XLSX export (read side).

### Out of scope
- **Accepting/rejecting suggestions** — no API exists (§7; proven by probe). Deferred to a future
  UI-automation backend.
- **Creating cell-anchored comments** — impossible via the API (Sheets comments are file-level).
- **File management** (upload/move/permissions), Gmail/Calendar/etc., real-time collaboration.
- **MCP server packaging** — the library is import-first; an MCP wrapper may be layered later but
  is not part of this spec.

---

## 2. Architecture

Two axes. **Comments are uniform** (one Drive API for all types); **content varies** (three APIs).
The design isolates them so all comment logic is written and tested once.

```
                 Workspace.open(id_or_url)
                          │  sniff mimeType via Drive files.get
        ┌─────────────────┼──────────────────┐
        ▼                 ▼                  ▼
      Doc               Sheet              Slides         ← VARIANT axis: content
        └─────────────────┴──────────────────┘
                          │  all inherit
                 Document + CommentsMixin                  ← UNIFORM axis: comments
                          │
                    Backend (ApiBackend)                   ← seam; future PlaywrightBackend
                          │
       google-api-python-client (drive v3 · docs v1 · sheets v4 · slides v1)
```

### Package layout (`src/` layout)
```
src/csa_google_workspace/
  __init__.py            # exports: Workspace, Doc, Sheet, Slides, exceptions, data classes
  auth.py                # OAuth installed-app flow + token cache; scope selection
  workspace.py           # Workspace: entry point / factory (open, open_by_url)
  backend.py             # Backend protocol; ApiBackend (the only backend in v1)
  _services.py           # lazy google-api-python-client resource handles
  base.py                # Document (abstract) + CommentsMixin
  comments.py            # Comment, Reply, Author, CommentCollection
  suggestions.py         # Suggestion + suggestion extraction (read-only)
  documents/
    doc.py               # Doc     — content read/write + suggestions
    sheet.py             # Sheet   — ranges + XLSX comment→cell mapping
    slides.py            # Slides  — slide/text read/write
  _cellmap.py            # XLSX export + threadedComments parse + fuzzy match (Sheets)
  _cache.py              # optional per-file cache (off by default)
  exceptions.py          # typed error hierarchy
tests/                   # pytest; unit tests use FakeBackend (no network)
```

### The Backend seam
`Backend` is a protocol abstracting the operations that *could* one day be done via UI automation.
v1 ships **only** `ApiBackend` (google-api-python-client). Operations the API cannot perform
(accept/reject suggestion, create a cell-anchored comment) raise `UnsupportedOperation` from
`ApiBackend`. This seam costs almost nothing now, is what unit tests inject a `FakeBackend` into,
and leaves room for a `PlaywrightBackend` later without reshaping the public API.

---

## 3. Authentication (`auth.py`)

OAuth **installed-app** flow, acting as a real person; comments/replies are attributed to that user.

```python
Workspace.from_oauth(
    client_secrets="client_secret.json",
    token_path="~/.csa_google_workspace/token.json",   # cached; auto-refreshes
    read_only=False,                                    # writes ON by default
)
Workspace.from_credentials(my_google_credentials)       # BYO credentials (user OAuth or service account)
Workspace(backend=my_backend)                           # advanced: inject a backend (service / custom / tests)
```

- **Scopes** are chosen from `read_only`:
  - `read_only=False` → `drive`, `documents`, `spreadsheets`, `presentations`.
  - `read_only=True` → the `.readonly` variants (`drive.readonly`, `documents.readonly`,
    `spreadsheets.readonly`, `presentations.readonly`) — defense-in-depth: even a bug cannot write.
- First run opens a browser and caches a refresh token; subsequent runs refresh silently.
- **Mode switching needs re-consent.** A token cached under `read_only=True` holds only `.readonly`
  scopes; later opening with `read_only=False` needs broader scopes. `auth.py` must detect the scope
  mismatch on the cached token and re-consent, rather than failing later with an opaque 403.
- **API enablement is separate from scope** (MEASURED: a scoped token still returns
  `403 SERVICE_DISABLED` until each API is enabled in the Cloud project). See §11 error handling.

---

## 4. Core objects (`base.py`)

```python
class Workspace:
    @classmethod
    def from_oauth(cls, client_secrets, token_path=..., read_only=False) -> "Workspace": ...
    def open(self, file_id_or_url: str) -> "Document":   # sniffs mimeType, returns Doc|Sheet|Slides
    def open_by_url(self, url: str) -> "Document": ...

class Document:                       # abstract base; never instantiated directly
    id: str
    name: str
    type: Literal["document", "spreadsheet", "presentation"]
    url: str
    mime_type: str
    read_only: bool
    # comments come from CommentsMixin; content from the subclass
    def reload(self) -> None:         # drop any cached state for this file
    def export(self, mime_type: str) -> bytes:   # Drive export (PDF/DOCX/XLSX/PPTX/…)
    def as_text(self) -> str:         # best-effort plain text (for LLM context); type-specific impl
```

`Workspace` holds credentials and **lazily** builds each of the four service clients on first use.
Opening a Sheet never initializes the Docs/Slides clients.

---

## 5. Comment surface (`comments.py`) — the uniform axis

Validated end-to-end by [`experiments/comment-lifecycle`](../../../experiments/comment-lifecycle/).

```python
class Author:
    display_name: str
    email: str | None        # frequently None — Google withholds it even when requested (MEASURED)
    is_me: bool              # reflects the authenticated identity vs the author (MEASURED reliable)
    photo_url: str | None

class Reply:
    id: str
    author: Author | None    # None on a deleted reply
    content: str | None      # None/"" on a deleted reply
    html_content: str | None
    action: Literal["resolve", "reopen"] | None
    deleted: bool
    created_time: datetime
    modified_time: datetime | None
    def edit(self, text: str) -> None
    def delete(self) -> None

class Comment:               # a top-level comment = the thread root
    id: str
    author: Author | None    # None when the comment is deleted (MEASURED: author is stripped)
    content: str | None      # None when deleted
    html_content: str | None
    quoted_text: str | None  # populated & reliable for Docs; usually absent for Sheets
    anchor: str | None        # raw anchor string; kix.* (Docs) or workbook-range JSON (Sheets)
    location: "Location | None"   # enriched best-effort (Sheets A1); see §8
    resolved: bool           # DERIVED: missing field ⇒ False (MEASURED: key absent until first resolve)
    deleted: bool
    created_time: datetime
    modified_time: datetime | None
    replies: list[Reply]

    def reply(self, text: str) -> Reply
    def resolve(self, text: str = "") -> Reply    # posts a content-less action reply (MEASURED OK)
    def reopen(self, text: str = "") -> Reply
    def edit(self, text: str) -> None             # author-only; AccessError otherwise
    def delete(self) -> None                       # soft delete

class CommentCollection:     # doc.comments
    def all(self) -> list[Comment]                 # auto-paginated
    def get(self, comment_id: str) -> Comment
    def filter(self, *, resolved: bool | None = None, author: str | None = None,
               since: datetime | None = None, include_deleted: bool = False) -> list[Comment]
    def __iter__(self) -> Iterator[Comment]

# on every Document (via CommentsMixin):
doc.comments                      # -> CommentCollection
doc.create_comment(text) -> Comment      # file-level; NO anchor param in v1 (see §8, §14.6)
```

### Behavioral contract (all MEASURED)
- **`resolved`**: the raw API omits the field until a resolve/reopen has ever occurred. The library
  normalizes **absent ⇒ `False`**.
- **Resolve/reopen**: performed as a reply carrying `action`; may be **content-less**. `.resolved`
  is read-back, never PATCHed.
- **Delete**: soft. The comment leaves `comments.list` unless `include_deleted=True`, and comes back
  with `author` **and** `content` stripped. `Comment`/`Reply` therefore make those `Optional`.
- **`fields` masks**: the library always requests the subfields needed to populate the model
  (`replies(...)`, `quotedFileContent`, `author(...)`), since the API returns nothing by default and
  bare `replies` come back empty.
- **Filtering**: `since` maps to server-side `startModifiedTime`; `include_deleted` to `includeDeleted`;
  `resolved`/`author` are applied client-side. Filtering is a first-class feature because large files
  overflow an LLM context window. (Note: `resolved`/`author` filtering still fetches all comments over
  the wire — it trims what reaches the caller/LLM, not what the API returns.)

### Object lifecycle (statefulness)
Model objects are **live for their own mutations, snapshots for everyone else's.** An action **updates
the object in place**: `comment.resolve()` sets `comment.resolved = True` and appends the action `Reply`
to `comment.replies`; `comment.reply(...)` appends; `comment.delete()` sets `deleted = True` and clears
`content`/`author` to mirror the server. But an object is **not** a live view of the file — edits made by
*other* users after the read are not reflected until `doc.reload()` (consistent with caching-off, §9).

### Author identity is limited (accepted)
Because `Author.email` is usually `None` (measured), the only *reliable* identity signal is `is_me`
("mine vs theirs"). Attributing a comment to a *specific other* person rests on `display_name`, which is
not unique. Adequate for triage; a hard requirement to identify individuals would push toward a different
auth model (e.g. a service account with directory access) — out of scope for v1.

---

## 6. Content read/write — the variant axis

Two **conveniences** on the base (`as_text`, `export`); everything else is type-specific. `as_text()` is a
best-effort flattening for LLM context, **not a uniform contract** — it means genuinely different things
per type (a doc's prose; a sheet's tab-joined grid, which can be huge; a deck's slide text), and `Doc`
overrides it with a `suggestions=` parameter the others lack. **Writes obey `read_only`**: when
`read_only=True`, every mutating call (content *and* comments) raises `ReadOnlyError`.

### `Doc` (`documents/doc.py`) — Docs API v1
```python
doc.as_text()                                   # walk body → paragraphs → text runs
doc.paragraphs                                  # structured read (headings, runs)
doc.replace_text("old", "new")                  # replaceAllText — the 80% review case
doc.insert_text(text, at: int)
doc.append_text(text)
doc.delete_range(start: int, end: int)
doc.batch_update([...])                         # raw Docs requests; indices applied back-to-front
doc.suggestions                                 # read-only; see §7
doc.as_text(suggestions="inline"|"accepted"|"rejected")   # Doc override, via suggestionsViewMode
```

### `Sheet` (`documents/sheet.py`) — Sheets API v4
```python
sheet.tabs                                      # worksheet names/ids
sheet.values("Sheet1!A1:D20")                   # -> list[list[str]]
sheet.as_text()                                 # tab-joined text
sheet.update("Sheet1!A1", [["x", "y"]])
sheet.clear("Sheet1!A1:D20")
sheet.batch_update([...])
sheet.comments_by_cell("B11")                   # read-only; via cell map (§8)
sheet.create_comment(text, cell="B11")          # file-level comment + clickable #range deep-link
```

### `Slides` (`documents/slides.py`) — Slides API v1
```python
slides.slides                                   # list[Slide]; slide.as_text(), slide.notes
slides.as_text()
slides.replace_text("old", "new")               # deck-wide replaceAllText
slides[2].insert_text("…")                       # PROVISIONAL — per-shape targeting unresolved (see §14.3)
slides.batch_update([...])
```

**Index safety (Docs/Slides):** `insert/delete` shift downstream indices, so multi-edit batches are
applied **back-to-front** by the helpers. `replace_text`/`append_text` are index-free and are the
recommended path; `batch_update` is the escape hatch for anything unwrapped.

> **Trade-off (accepted):** `batch_update()` takes **raw Google API request dicts**, so callers using it
> couple to `google-api-python-client` request shapes — a deliberate hole in the abstraction so we never
> *block* an advanced edit we didn't wrap. The high-level helpers are the clean, stable surface.

---

## 7. Suggestions (`suggestions.py`) — read-only

Settled by [`experiments/docs-suggestions`](../../../experiments/docs-suggestions/) and
[`research/docs-suggestions-reference.md`](../../../research/docs-suggestions-reference.md).

```python
class Suggestion:
    suggestion_id: str
    kind: Literal["insertion", "deletion"]
    text: str                 # the suggested text (runs sharing an id are grouped)
    # NO author / timestamp — the Docs API does not expose them (MEASURED)

doc.suggestions               # -> list[Suggestion]  (grouped by suggestion id)
doc.as_text(suggestions="accepted")   # PREVIEW_SUGGESTIONS_ACCEPTED
doc.as_text(suggestions="rejected")   # PREVIEW_WITHOUT_SUGGESTIONS
```

- **No `accept()`/`reject()`** — proven impossible via full API enumeration (3 methods, 40
  `batchUpdate` request types, zero suggestion ops). `ApiBackend` would raise `UnsupportedOperation`
  if such a method existed; the public API simply does not offer one in v1.
- **No `Suggestion.author`** — not derivable.
- Suggested **deletions** are handled by the same code path (`suggestedDeletionIds`) but were not
  exercised by a live fixture — flagged as an implementation-time verification.

---

## 8. Sheets cell mapping (`_cellmap.py`) — best-effort read side

The differentiator; the one hard read path. Grounded in the anchor probe + reference §7.

```python
class Location:              # comment.location for a Sheet (None when unresolved)
    tab: str                 # worksheet name
    cell: str                # A1, e.g. "B11"
    row: int                 # 1-based
    col: int                 # 1-based
```

- The Drive `anchor` for Sheets is `{"type":"workbook-range","range":"<opaque id>"}` — **not**
  A1-decodable. Mapping requires **XLSX export** → parse `xl/threadedComments/*.xml` (`ref="B11"`)
  → match back to Drive comments. **The match key is weaker than it first looks:** the XLSX author is an
  opaque `personId` (resolving it to a name needs `xl/persons/person*.xml`), and the XLSX `dT` timestamp's
  correlation with the Drive `createdTime` is **unverified** (deferred probe below). In practice the
  reliable key may reduce to **content + approximate time**, which collides when one author repeats text.
- `comment.location` is populated lazily on first access; the export + parse + match result is cached
  per file. Matching is **heuristic**: on no confident match it yields `None` — never a wrong guess.
- **Creating** a cell-anchored comment is impossible; `sheet.create_comment(text, cell=...)` makes a
  file-level comment with a clickable `#gid=…&range=…` deep-link in the body (honest about being a link).

### Deferred validation (Probe 2 — decision 2026-07-20)
The single-comment read path is proven. **At-scale matching robustness** (author+content+timestamp
collisions, timestamp precision across Drive JSON vs XLSX `dT`) and the **~10 MB `files.export` cap**
(which would make mapping unavailable on large sheets) are to be validated with a dense/large fixture
during the cell-mapper build. `_cellmap` must degrade to `location=None` + a recorded warning when the
export fails or a match is ambiguous.

---

## 9. Caching (`_cache.py`) — off by default

- Default: **no caching** (or a short TTL if explicitly enabled). Rationale: the tool is used during
  **live multi-reviewer sessions**; a cache invalidated only on *our* writes would show stale
  resolution/new comments authored by others.
- When enabled (`Workspace(..., cache_ttl=…)`), caches per `fileId`: comment list, derived XLSX cell
  map (the expensive part), content snapshots. Invalidated on any write we perform and by TTL.
  `doc.reload()` always forces a refresh.
- **No persistent storage** of comment content (privacy; matches the repo's gitignore stance).

---

## 10. Error hierarchy (`exceptions.py`)

Wraps `googleapiclient.errors.HttpError` so callers never touch raw HTTP.

```
CsaWorkspaceError
├─ AuthError             # bad/expired creds, consent needed
├─ ServiceDisabledError  # 403 reason=SERVICE_DISABLED — names the API + activation URL (MEASURED need)
├─ ReadOnlyError         # mutation attempted while read_only=True
├─ NotFoundError         # 404 — missing file/comment/reply
├─ AccessError           # 403 — not shared / insufficient scope / editing another's comment
├─ RateLimitError        # 429 — carries retry_after; auto-retried with exponential backoff
├─ UnsupportedOperation  # API-impossible ops (accept/reject suggestion, cell-anchored create)
└─ ApiError              # catch-all wrapper: status, reason, raw HttpError
```
Transient `429`/`5xx` are retried with backoff; everything else raises immediately.
`ServiceDisabledError` is broken out because it is a first-run stumbling block with a specific fix
(enable the API in the Cloud project) — the message includes which API and the console URL.

---

## 11. Testing (`pytest`)

- Unit tests inject a **`FakeBackend`** replaying **sanitized/synthetic fixtures** derived from the probe
  transcripts (the raw transcripts are gitignored — they hold real emails/comment text, so fixtures must
  be scrubbed before committing) — no network, no credentials. This exercises the entire domain layer
  (threading, resolve/delete normalization, cell matching, suggestion grouping, error mapping).
- Heaviest coverage on the fragile bits: **cell mapping** (synthetic XLSX fixture: merged cells,
  multiple tabs, named ranges, duplicate author+text), **`resolved` absent⇒false**, **deleted-comment
  field stripping**, **suggestion run-grouping**, **error classification** (esp. `SERVICE_DISABLED`).
- A small **live integration suite**, gated behind an env var + real fixtures (a Doc/Sheet/Slides the
  developer owns), mirrors the probes. Mutating integration tests create and trash their own fixtures.

---

## 12. Build sequence

All three file types are first-class, but the build is internally sequenced so there's a usable
milestone early:

1. **Foundations** — `auth`, `Workspace`, `Backend`/`ApiBackend`, `Document`, error hierarchy, `FakeBackend`.
2. **Comments across all three types** — `Comment`/`Reply`/`Author`/`CommentCollection`, full lifecycle.
   *(Usable milestone: read + triage + reply + resolve on any file.)*
3. **Content read** — `as_text`/`export`; `Doc.paragraphs`, `Sheet.values`, `Slides.slides`.
4. **Sheets cell mapping** — `_cellmap` + `comments_by_cell` (runs the deferred at-scale/export-cap probe).
5. **Content write** — `replace_text`/`append_text`/`insert`/`delete` + `batch_update` per type; `read_only` gate.
6. **Suggestions (read-only)** — `doc.suggestions`, `doc.as_text(suggestions=…)`.

---

## 13. Future directions (not in v1)
- **`PlaywrightBackend`** — the long-term plan for operations the APIs cannot do (accept/reject
  suggestions; true cell-anchored Sheets comments). A browser drives the real editor UI. Principle:
  **API-first, UI-automation only for the genuinely-impossible** — never for something the API can do.
  Because callers only touch the public API (`suggestion.accept()`), adding it later is a config change,
  not an API change: `ApiBackend` raises `UnsupportedOperation` today; a `PlaywrightBackend` fulfils it
  tomorrow (hybrid per-operation routing). **Hard problems to solve first:** browser auth ≠ API auth (a
  logged-in *session*/cookies, 2FA, expiry — the biggest hurdle and a security concern); UI fragility
  (Google restyles without notice); speed (seconds/op, needs a browser present); Terms-of-Service.
  **Alternatives considered:** the editor's undocumented internal RPC (faster, more fragile, higher ToS
  risk) and Apps Script (likely the same suggestion gap). **Phasing:** before building, a throwaway
  `experiments/playwright-accept/` **spike** answers the riskiest question first — "can we hold a usable
  authenticated browser session and reliably click Accept?" — documented in the same empirical style.
- **MCP server wrapper** — expose the library's operations as MCP tools.
- **Async API** — v1 is synchronous (matches `google-api-python-client`, `gspread`); async could layer later.

---

## 14. Open risks (carried into the plan)
1. **Sheets at-scale mapping + 10 MB export cap** (§8) — deferred probe; must degrade gracefully.
2. **Suggested deletions** — mechanism assumed symmetric; verify with a fixture (§7).
3. **Slides per-shape editing** — object-ID targeting is the least-specified write surface; keep to
   deck-wide `replace_text` + `batch_update` until validated.
4. **Multi-writer staleness** — mitigated by caching-off default; document that reads are point-in-time.
5. **`read_only` → read-write mode switching** — a cached narrow-scope token needs detected re-consent (§3).
6. **Docs comment *creation* anchoring** — reading Docs anchors works (`quoted_text`), but creating a
   *text-anchored* Docs comment via the API is unverified; v1 creates file-level only. A probe should
   confirm whether Docs-create anchoring is worth adding later.

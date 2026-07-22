# Changelog

## 2026-07-22 — Live-suite coverage for Tier 3 + a dedicated OAuth e2e suite

Test-only; all gated behind `CSA_GW_INTEGRATION` (no runtime change):

- Extended the live suite to exercise the Tier 3 additions against real Google:
  `Sheet.append_rows`, multi-tab `as_text` (`# <tab>` headers + `tab=`), and
  `Slides.insert_text` / `Slide.shape_ids`.
- New **`tests/integration/test_oauth_live.py`** — end-to-end OAuth: a real `from_oauth`
  login that reaches Google, token-file permissions (no group/other access), and the
  `read_only` session contract (reads succeed, writes raise `ReadOnlyError`). Because the
  writable login runs first, the read-only test reuses the cached token without re-prompting.
- Gated integration tests: 6 → 9.

## 2026-07-21 — Tier 3 API-surface additions

Closed the remaining within-scope content-write gaps (all `read_only`-gated, TDD):

- **Sheets `append_rows(a1_range, values, value_input_option="RAW")`** — `values.append`
  with `INSERT_ROWS`. Non-idempotent, so it is never auto-retried on 5xx (a retry could
  duplicate rows). Invalidates the cell-map cache like the other writes.
- **`Sheet.as_text(tab=None)`** now renders **every** tab by default (each prefixed with a
  `# <tab>` header when there's more than one), fixing silent first-tab-only truncation on
  multi-tab sheets. `tab=` selects a single tab (no header); single-tab output is unchanged.
- **Slides `insert_text(object_id, text, index=0)`** — per-shape text insertion, symmetric
  to `Doc.insert_text` but shape-addressed. **`Slide.shape_ids`** lists the text-capable
  shape objectIds to target. (A fuller shape-CRUD model stays out of scope; `batch_update`
  remains the escape hatch.)

## 2026-07-21 — Dev tooling: ruff + mypy + coverage gates

Formalized the quality bar as enforced CI gates (no runtime/API change):

- **ruff** (lint): rule set `E,F,W,I,B,UP`, line-length 120, ignoring `E702` (the
  deliberate one-line `x; y` style). No auto-formatter — the dense style is intentional.
- **mypy**: `check_untyped_defs`, google/defusedxml marked as missing-stubs. Fixed the
  real gaps it surfaced — typed the injected `_backend`/`_file_id`/`_comment_id` fields on
  `Comment`/`Reply` and declared `CommentsMixin`'s subclass-provided attributes.
- **coverage** (`pytest-cov`): enforced on the CI matrix with `fail_under = 85` (total
  ~87%; the gap is the integration-only `ApiBackend` calls + interactive OAuth flow).
- CI now has a dedicated `lint` job (ruff + mypy) alongside the 3.10–3.13 `test` matrix.

## 2026-07-21 — Packaged for PyPI (v0.1.0)

First release-ready packaging pass, alongside the correctness fixes from an external audit.

- **PyPI metadata.** `pyproject.toml` now carries `readme`, an SPDX
  `license = "Apache-2.0"` + `license-files`, `authors`/`maintainers`, `keywords`,
  trove `classifiers` (incl. `Typing :: Typed`), and `[project.urls]`. The version is
  single-sourced from `csa_google_workspace.__version__` via `dynamic`/`attr` (no more
  two-places-to-bump drift). `python -m build` + `twine check` pass for both sdist and wheel.
- **`py.typed` (PEP 561)** ships, so downstream mypy/pyright consume the inline type hints.
- **Typed errors from `open()`.** `ApiBackend.get_file_metadata` now routes through the
  error translator; the first call no longer leaks a raw `HttpError` on a
  missing/forbidden/service-disabled file — it raises the typed `NotFoundError` /
  `AccessError` / `ServiceDisabledError` the spec promises.
- **Cell-map degrade is now a recorded warning** (stdlib `logging`), not silence — so an
  export-cap / access / malformed-XLSX failure is distinguishable from a genuine no-match.
- **CI.** GitHub Actions runs the unit suite on Python 3.10–3.13 for every push and PR
  (the live Google suite stays gated behind `CSA_GW_INTEGRATION`).
- **License consolidated to Apache-2.0.** A single `LICENSE` (the earlier dual
  MIT/Apache `LICENSE-MIT` + `LICENSE-APACHE` files were removed).
- Version bumped `0.0.1 → 0.1.0`.

## 2026-07-20 — Lifecycle & suggestions probes (empirical)

Two new live-API probes under `experiments/`, each with a `RESULTS.md`, plus an
`experiments/README.md` index and shared-setup guide.

- **`experiments/comment-lifecycle/`** — exercised the full comment/reply cycle on a
  self-created, self-trashed throwaway Sheet. **Corrected two things in the reference doc:**
  (1) `resolved` is **absent** on a fresh comment, not `false` — it appears only after a
  resolve/reopen action (treat missing as false); (2) delete is soft and strips **author**
  as well as content, and the comment drops out of `comments.list` unless `includeDeleted=true`.
  Also confirmed: action-replies (`resolve`/`reopen`) can be **content-less**, `author.me`
  exists, and `emailAddress` is withheld even when requested.
- **`experiments/docs-suggestions/`** — settled the Docs "suggesting mode" question against a
  live doc. **Reading suggestions works** (via `suggestionsViewMode`, incl. accepted/rejected
  text previews), but **accepting/rejecting is impossible via the API** — proven by enumerating
  the entire Docs API surface (3 methods, 40 `batchUpdate` request types → zero suggestion ops).
  Suggestion **author/timestamp is not exposed**. Bonus: Docs comments carry `kix.*` anchors
  **and populated `quotedFileContent`**, so Docs comment→location mapping is trivial (unlike Sheets).
- **New reference:** `research/docs-suggestions-reference.md` (suggestions are read-only;
  no accept/reject; author unavailable; UI-automation is the only path to accept/reject).
- **Setup finding:** a correctly-scoped OAuth token still 403s with `SERVICE_DISABLED` until
  each API (Docs/Sheets/Slides) is separately enabled in the Cloud project — scope ≠ enablement.

## 2026-07-09 — Structured comment extractor

Added `experiments/anchor-probe/extract_comments.py`: extracts **all comments from any Drive file type** (Docs/Sheets/Slides/Drawings/blobs) into structured JSON — author, timestamps, content/htmlContent, resolved/deleted, quotedFileContent, raw anchor, and full reply threads (with `resolve`/`reopen` actions). For Sheets it resolves each comment's **A1 cell** best-effort via the XLSX-export join. Verified against the live sheet: correctly mapped the UI comment to B11 and the mislanded API comment to A1, with threads intact. Notes captured: `author.emailAddress` is often absent; @mentions are plain text in `content` but linkified in `htmlContent`. Extractor JSON output is gitignored (may contain real comment data).

## 2026-07-09 — Anchor probe run: empirical correction

Ran `experiments/anchor-probe` against a live sheet. Results captured in `experiments/anchor-probe/RESULTS.md`. This **corrected a conclusion** in the reference doc:

- **"Sheets anchors are opaque" was too strong.** A UI-placed comment's real anchor is `{"type":"workbook-range","uid":0,"range":"1453957822"}` — **structured**, format `workbook-range` (which a prior entry wrongly called folklore). But `range` is an opaque internal id, so the anchor is still **not A1-decodable**. Reworded §7 and the TL;DR accordingly; moved `workbook-range` out of the "folklore" list.
- **Write limitation confirmed empirically:** an API comment anchored to B11 was stored verbatim but landed on A1 in the export — the editor ignores anchor coordinates.
- **XLSX read path confirmed empirically:** comments export to `xl/threadedComments/threadedComment*.xml` (mirrored in `xl/comments*.xml`) with real A1 `ref`s (recovered `ref="B11"`). Sheets comments are *threaded comments*.
- **Resolved the a-bonus discrepancy:** its `{a:[{sht:{rng:{r,c}}}]}` parser shape is not what real UI comments return; the anchor is not an A1 source. Updated `server-landscape.md`.

## 2026-07-09 — Server landscape & anchor probe

Added, without changing existing conclusions:

- **`research/server-landscape.md`** — source-verified survey of MCP servers that handle Google comments (read from actual tool definitions, not READMEs). Ranked for "general Drive server with proper comments": **#1 a-bonus/google-docs-mcp** (only one that engineers around the Sheets limitation — cell-link + native cell note + read-side anchor mapping), **#2 taylorwilsdon/google_workspace_mcp** (broadest & most adopted, but file-level Sheets comments only, no delete/edit), **#3 piotr-agier/google-drive-mcp** (best Docs anchoring, no Sheets comments). Confirmed no server truly anchors Sheets comments — the ceiling is Google's Drive API. Official Google Workspace MCP has no comment tools.
- **`experiments/anchor-probe/`** — runnable Python script to empirically settle how Sheets comment anchors behave (create / dump-raw-anchor / xlsx-export), the one claim currently supported only by documentation.
- **Flagged an open discrepancy to verify:** a-bonus's `commentAnchor.ts` parses a concrete Sheets anchor shape `{a:[{sht:{sid,rng:{r,c}}}]}`. If real, UI-created Sheets comments are anchor-parseable, which would partly revise the reference doc's "anchors are opaque" conclusion. The probe will settle it; the reference doc is left unchanged until then.

## 2026-07-09 — Research refresh & consolidation

Verified the research against current Google Workspace documentation, the MCP specification, and the MCP server ecosystem (all as of July 2026), corrected what was wrong, and consolidated 5 overlapping documents into 3.

### Document structure

Consolidated to reduce duplication:

| Before | After |
|--------|-------|
| `Google Drive API Comment-Related Capabilities.md` + `report-claude.md` + `report-chatgpt.md` | **`google-drive-comments-reference.md`** — one canonical "how it works" reference |
| `Google Sheets Comments MCP Server - Design Document.md` | **`mcp-server-design.md`** — corrected, with a 2026 reality check |
| `llms-full.md` (scraped MCP docs) | **`mcp-protocol-notes.md`** — concise, current |

### Corrections

**Google Drive comments API**
- **Method count: 12 → 10.** 5 on `comments`, 5 on `replies`. There is **no `patch` method** in v3 — `update` uses the PATCH verb; `comments.patch`/`replies.patch` were v2-only.
- **`fields` parameter is REQUIRED** on every comments/replies method except `delete` (was not stated).
- **`resolved` is read-only** — resolve/reopen only via a reply with `action: "resolve" | "reopen"` (clarified).
- **Deletion is soft** for both comments and replies (`deleted: true`, content stripped) — confirmed.
- **Removed a fake OAuth scope.** `https://www.googleapis.com/auth/drive.comments` does not exist; corrected to the real `drive` / `drive.file` / `drive.readonly` scopes.
- **Switched v2 → v3 examples.** `report-claude.md` used deprecated v2 endpoints (`/v2/files/...`, `comments.insert`); v3 is current. (v2 is legacy/migration-encouraged but has no announced sunset date as of July 2026.)

**The `anchor` field (the big one)**
- **Cell-anchored comments cannot be created via the Drive API.** Google Workspace editors treat API-set anchors as *unanchored*; a Sheets comment created via the API lands at file level, not on the target cell. This invalidates the original "spatial index for writes" architecture.
- **Reading a comment's cell requires an XLSX-export-and-parse detour**, not the `anchor` field, which is opaque for Sheets.
- **Debunked folklore anchor formats.** `R1C2`, `sheet_id=...&range=A1`, and the `cell_classifier`/`range_classifier` JSON in the original doc had no primary source and were removed / relabeled as speculative.
- Clarified **notes vs comments**: notes (Sheets API) are genuinely cell-anchored; comments (Drive API) are not.

**Market analysis**
- **"0% of MCP servers support comments / 100% greenfield / first-mover advantage" is false.** At least 5–6 servers now implement Google comment lifecycles (a-bonus, piotr-agier, taylorwilsdon's workspace server, dbuxton, and others). The obsolete "8 servers, 0% support" table was removed. The real unsolved problem — and the defensible differentiator — is reliable UI-visible/cell-mapped anchoring, which competitors document as broken or missing.

**MCP protocol**
- Current stable spec is **`2025-11-25`**, not `2025-06-18`.
- **Streamable HTTP** replaced the old HTTP+SSE transport (as of `2025-03-26`).
- Added notes on Elicitation, the OAuth 2.1 authorization framework, and structured tool output. Flagged the breaking `2026-07-28` release candidate.

### Method
Facts were verified against primary sources (Google's API reference and guides, the official MCP spec, and server source/READMEs). One area remains genuinely uncertain: the exact current status of Google Issue Tracker threads [#292610078](https://issuetracker.google.com/issues/292610078) and [#357985444](https://issuetracker.google.com/issues/357985444) — both are sign-in-gated, so the *behavior* they describe is confirmed but their live status labels could not be scraped.

# Google Sheets Comments MCP Server — Design Document

> **Refreshed July 2026.** The original design (Sept 2025) rested on two assumptions that no longer hold. Read the reality check before the rest. Factual API behavior lives in [`google-drive-comments-reference.md`](./google-drive-comments-reference.md); MCP protocol facts in [`mcp-protocol-notes.md`](./mcp-protocol-notes.md).

---

## ⚠️ 2026 Reality Check (read first)

The original document made two claims that drove its whole thesis. Both are now false or unworkable:

1. **"Zero MCP servers support comments — 100% greenfield, first-mover advantage."**
   **False as of 2026.** At least 5–6 actively-maintained servers implement Google comment lifecycles (list/create/reply/resolve), including [a-bonus/google-docs-mcp](https://github.com/a-bonus/google-docs-mcp), [piotr-agier/google-drive-mcp](https://github.com/piotr-agier/google-drive-mcp), [taylorwilsdon/google_workspace_mcp](https://github.com/taylorwilsdon/google_workspace_mcp) (Docs + Sheets + Slides), and [dbuxton/google-docs-mcp](https://github.com/dbuxton/google-docs-mcp). This is a **crowded space**, not a greenfield.

2. **"Spatially index comments by cell/row/column for instant filtering."**
   **Unworkable for writes, and the read path is different than assumed.** Cell-precise anchoring cannot be created through the Drive API — the Sheets UI treats API anchors as *unanchored* ([details](./google-drive-comments-reference.md#7-the-anchor-field--the-hard-truth-for-sheets)). Reading a comment's cell requires an **XLSX-export-and-parse** detour, not the `anchor` field. The original "spatial index" architecture assumed both directions worked; they don't.

**What is still true and valuable:** comments are a Drive-API-v3 concern; large sheets *do* overflow AI context windows, so filtering/summarization is genuinely useful; and reading + triaging *existing* comments is fully achievable.

**The defensible differentiator today** is *not* "we do comments." It is **(a) reliable read-side cell mapping for Sheets** (via XLSX export — most servers don't do this) and/or **(b) doing Sheets/Slides comment coverage well**, since competitors document those as broken or missing.

---

## 1. Recommended scope (revised)

A **read-focused comment-triage server** for Google Sheets, positioned against existing servers rather than as a first mover.

### In scope
- ✅ List / read comments and replies (Drive API v3)
- ✅ **Read-side cell mapping** for Sheets via XLSX export → A1 notation (the hard part others skip)
- ✅ Filtering & summarization: by resolution status, author, date, and — for reads — by cell/row/column derived from the XLSX map
- ✅ Create comments, replies, resolve/reopen (accepting they are **file-level**, with an optional clickable cell hyperlink in the body)
- ✅ Context management so thousands of comments don't overflow the model

### Out of scope
- ❌ Writing cell-*anchored* comments (not possible via the API — see reality check)
- ❌ Reading/writing cell **data** (belongs to a separate Sheets MCP server)
- ❌ Native @mention notifications beyond what Drive already sends
- ❌ Real-time collaboration

> If cell-attached text is a hard requirement, expose a **Sheets *note*** tool (Sheets API) instead of pretending comments can anchor.

---

## 2. Architecture

```
MCP Host (Claude Desktop, IDE, etc.)
        │  JSON-RPC 2.0 over stdio (local) or Streamable HTTP (remote)
        ▼
Comments MCP Server
  ├─ Drive API gateway        → comments/replies CRUD
  ├─ XLSX export + parser      → comment → A1 cell mapping (read side)
  ├─ In-memory cache           → per fileId, with invalidation
  └─ Filter / summarize layer  → keep model context small
        │
        ▼
Google Drive API v3  (+ Drive export endpoint; Sheets API only if notes are added)
```

### Cache
In-memory only (no persistent comment storage). Keyed by `fileId`. Invalidate on any write (create comment/reply, resolve, delete) and on a configurable max age. Cache both the comment list and the derived XLSX cell map, since the export call is the expensive part.

### Read-side cell mapping (the differentiating component)
On first read (or refresh) for a spreadsheet: export as XLSX, parse `xl/comments*.xml` + worksheet XML, and build `commentText/author → A1` associations. Match Drive-API comments to XLSX-parsed positions by author + content + timestamp. Document this as best-effort (matching is heuristic) and degrade gracefully to file-level when a match isn't found.

---

## 3. Proposed MCP tools

Read/triage (the core value):
- `list_comments(fileId, {resolved?, author?, since?, includeReplies?, forceRefresh?})`
- `get_comment(fileId, commentId)`
- `get_comments_for_cell / _row / _column(fileId, ref)` — **read-only**, resolved via the XLSX cell map, clearly documented as best-effort
- `summarize_comments(fileId, {filter})` — collapse large threads for the model

Write (clearly labeled file-level):
- `create_comment(fileId, content, {cellLink?})` — optional hyperlink to a cell in the body; **not** anchored
- `reply_to_comment(fileId, commentId, content)`
- `resolve_comment / reopen_comment(fileId, commentId)` — via reply `action`
- `delete_comment(fileId, commentId)` — soft delete

Cache:
- `refresh_comments(fileId)`, `get_cache_status(fileId)`

Optional (only if cell-attached text is required):
- `set_cell_note(spreadsheetId, a1, text)` — **Sheets API**, genuinely cell-anchored

> Every tool that touches comments must set the Drive API `fields` parameter (required — see the reference doc).

---

## 4. Auth
OAuth 2.0 (service account for servers, or user OAuth). Scopes: `drive.readonly` for a read-only build; `drive.file` (preferred) or `drive` for writes; add `spreadsheets`/`spreadsheets.readonly` only if the notes tool is included. Default the server to **read-only**; require explicit `enable_write` to expose mutating tools. (There is no `drive.comments` scope.)

---

## 5. Tech stack
- **TypeScript** + [`@modelcontextprotocol/sdk`](https://github.com/modelcontextprotocol/typescript-sdk) + [`googleapis`](https://www.npmjs.com/package/googleapis)
- An XLSX/zip parser for the read-side mapping (e.g. a zip reader + XML parser; no heavyweight spreadsheet lib needed)
- **Transports: stdio (primary) and Streamable HTTP (remote).** Do **not** target the old standalone HTTP+SSE transport — it was replaced by Streamable HTTP in the 2025-03-26 spec. See [`mcp-protocol-notes.md`](./mcp-protocol-notes.md).
- Jest, ESLint + Prettier, GitHub Actions

---

## 6. Testing focus
- **Anchor/mapping reality tests first**: build a synthetic sheet with human-placed cell comments; assert the XLSX-export path recovers correct A1 references; assert (and document) that API-created anchors come back unanchored.
- Cache invalidation correctness after each write type.
- `fields`-parameter presence on every comments/replies call.
- Scale: 1,000+ comments, summarization keeps context bounded.

---

## 7. Risks
- **Google could change the XLSX-export comment format** — the read-side mapping is reverse-engineered, not a supported API. Pin tests against real exports and monitor.
- **Anchoring may silently start/stop working** if Google fixes the tracker issues — treat file-level as the contract, anchoring as a bonus.
- **Crowded market** — lead with the read-side cell mapping and Sheets coverage, not "we support comments."

---

## Appendix: what was cut from the original
The original 10-week, 5-phase plan and the "spatial indexing engine" (cell→commentId index built for *both* read and write) assumed cell anchoring worked. The spatial index survives only as a **read-side** structure fed by the XLSX map. The market-analysis sections ("100% greenfield", the 8-server "0% support" table) are obsolete and were removed; see `../CHANGELOG.md`.

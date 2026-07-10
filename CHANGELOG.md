# Changelog

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

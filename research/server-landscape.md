# MCP Server Landscape — Who Handles Google Comments (and How)

> **Surveyed July 2026**, verified against each server's actual source (tool definitions), not just READMEs. This is the "prior art" the design doc's market section used to hand-wave. See [`mcp-server-design.md`](./mcp-server-design.md) for why this matters and [`../CHANGELOG.md`](../CHANGELOG.md) for history.

## The one fact that shapes everything

**No MCP server can anchor a comment to a specific Google Sheets cell — because the ceiling is in Google's Drive API, not the servers.** The Drive `comments` API is the only cross-app comment API, and comments it creates land in the file-level "All comments" pane, not on a cell. Every server inherits this. The only real differentiator is **how gracefully each works around it.**

## Ranked for "a general Drive MCP that handles comments properly (esp. Sheets)"

### 1. a-bonus/google-docs-mcp — best comment handling
- <https://github.com/a-bonus/google-docs-mcp> · TypeScript · ~607★ · v1.11.0 (Jun 2026), active
- **General** Google suite: Docs, Sheets (+tables), Drive files/folders, Gmail, Calendar.
- **Comments: full CRUD** for both Docs *and* Sheets — `list/get/add/reply/resolve/**delete**`, via a dedicated `src/tools/sheets/comments/` module.
- **Sheets workaround (the standout), attacks the gap three ways:**
  1. `createSheetsComment` with `includeCellLink=true` embeds a clickable `…/edit#gid=…&range=A1` deep-link in the comment body.
  2. `createSheetsCellNote` writes a **native Sheets cell note** (Sheets API) — genuinely cell-attached, though a note (not a resolvable thread).
  3. `commentAnchor.ts` does **read-side location mapping**, parsing both deep-links and a Drive anchor JSON shape `{ a: [{ sht: { sid, rng: {r, c} } }] }`.
- ⚠️ That third point matters beyond this doc — see "[Open discrepancy](#open-discrepancy)" below.
- **Verdict:** best fit for the stated goal — general, and the only one that seriously engineers around the Sheets limitation.

### 2. taylorwilsdon/google_workspace_mcp — broadest & most adopted
- <https://github.com/taylorwilsdon/google_workspace_mcp> · Python · ~2.8k★ · v1.22.0 (Jun 2026), very active · MIT
- **Widest coverage of any server:** Drive, Docs, Sheets, Slides, Gmail, Calendar, Contacts, Tasks, Forms, Chat, Apps Script, Search. Auth: OAuth 2.0/2.1 **+ service accounts**; transports: stdio **+ Streamable HTTP**.
- **Comments: list / create / reply / resolve** across Docs, Sheets, Slides (shared `core/comments.py` factory). **No delete, no edit, no reopen** (issue [#487](https://github.com/taylorwilsdon/google_workspace_mcp/issues/487) open).
- **Sheets anchoring: not addressed** — `_create_comment_impl` sends only `{"content": …}`; comments are file-level. Cell-anchoring request [#788](https://github.com/taylorwilsdon/google_workspace_mcp/issues/788) is open and stale. Its `manage_spreadsheet_comment` docstring **misleadingly** claims cell-scoping the code doesn't do.
- **Docs read side is excellent:** `get_doc_as_markdown` inlines anchored comments with their anchor text — great for review workflows.
- **Verdict:** pick for breadth, maturity, and enterprise auth; accept file-level Sheets comments.

### 3. piotr-agier/google-drive-mcp — best Docs anchoring, no Sheets comments
- <https://github.com/piotr-agier/google-drive-mcp> · TypeScript · ~182★ · v2.2.0 (Apr 2026), active
- General Drive/Docs/Sheets/Slides/Calendar. Comments are **Docs-only** (`list/get/add/reply/delete`), with notable Docs anchoring via Docs-API text-matching + a DOCX-export fallback. **No Sheets comment tools.**
- **Verdict:** strong for anchored *Docs* comments; not a fit if Sheets is the priority.

### Also-rans
- **us-all/google-drive-mcp-server** (TS, brand-new, ~0★): broad tool count, file-level Drive comments only, unproven. Watch, don't adopt.
- **Managed platforms — Composio, Klavis AI, Pipedream** (hosted): convenient OAuth, but all expose **file-level** Drive comments only; none solve Sheets cell mapping. (Pipedream is being acquired by Workday.)
- **Official Google Workspace MCP** (<https://developers.google.com/workspace/guides/configure-mcp-servers>): Developer Preview; Gmail/Drive/Calendar/Chat/People — **no comment tools at all.**
- **Anthropic's built-in Google Workspace connector**: retrieval-oriented; no comment-write tooling.

## Summary

| Server | General? | Sheets comments | Delete/edit | Sheets anchoring workaround | Adoption |
|---|---|---|---|---|---|
| **a-bonus/google-docs-mcp** | ✅ | ✅ full CRUD | ✅ | ✅ cell-link + cell-note + read mapping | ~607★ |
| **taylorwilsdon/google_workspace_mcp** | ✅✅ (12+ svcs) | ✅ create/reply/resolve | ❌ | ❌ file-level only | ~2.8k★ |
| **piotr-agier/google-drive-mcp** | ✅ | ❌ (Docs only) | Docs only | n/a | ~182★ |

**Recommendation:** `a-bonus/google-docs-mcp` for comment quality on Sheets; `taylorwilsdon/google_workspace_mcp` if breadth and enterprise auth outweigh Sheets-comment precision.

## Open discrepancy

`a-bonus`'s `commentAnchor.ts` parses a concrete Sheets anchor structure — `{ a: [{ sht: { sid, rng: {r, c} } }] }`. If UI-created Sheets comments really carry that, then the read path is **anchor-parseable**, partly contradicting the reference doc's "anchors are opaque, use XLSX-export" conclusion. This is a *different* shape from the `cell_classifier` folklore we debunked, so both can hold. **Unresolved until measured** — the [`experiments/anchor-probe`](../experiments/anchor-probe/) script dumps a real anchor to settle it; findings will be folded back into the reference doc.

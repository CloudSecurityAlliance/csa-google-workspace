# MCP Server Landscape — Who Handles Google Comments (and How)

> **First surveyed July 2026; re-verified 2026-08-31** — star counts and last-push dates from the
> GitHub API, tool lists and comment support from each project's own tool reference or source, not
> from its README's claims. This is the "prior art" the design doc's market section used to hand-wave. See [`mcp-server-design.md`](./mcp-server-design.md) for why this matters and [`../CHANGELOG.md`](../CHANGELOG.md) for history.

## Re-verification, 2026-08-31

Seven weeks on, three things moved enough to matter. Numbers below are from the GitHub API and
each project's own tool reference.

| server | ★ (Jul → Aug) | last push | change |
|---|---|---|---|
| taylorwilsdon/google_workspace_mcp | 2.8k → **3095** | 2026-08-30 | still the broadest and most adopted; comment gaps **unchanged** |
| a-bonus/google-docs-mcp | 607 → **649** | 2026-08-10 | unchanged in substance |
| piotr-agier/google-drive-mcp | 182 → **209** | 2026-08-21 | **grew enormously** — see below |
| isaacphi/mcp-gdrive | — → 283 | **2025-05-07** | popular and **abandoned ~16 months** |
| felores/gdrive-mcp-server | — → 72 | **2025-11-07** | **stale ~10 months** |
| aaronsb/google-workspace-mcp | *(new to this survey)* 171 | 2026-08-31 | Gmail/Calendar/Drive; no comment tools |

**piotr-agier is the significant change: v2.6.0 now ships 115 tools** (its README says 116; its
own `docs/tools.md` lists 115) — Shared Drives, permissions, revisions, surgical Docs editing,
Sheets formatting, Slides authoring, PDF ingestion, Calendar. It is now **larger than this
project's 58**, and the July entry calling it a Docs-anchoring specialist understates it.

**But its comment surface is unchanged and still Docs-only:** `listComments`, `getComment`,
`addComment`, `replyToComment`, `deleteComment`. Read from `docs/tools.md` — **no resolve, no
reopen, and no Sheets or Slides comments at all.** Its Docs read side remains the best of the
field: character offsets plus a two-tier anchor (Docs API text matching, DOCX-export fallback).

**taylorwilsdon's two gaps are both still open**, verified by issue state rather than inferred:
[#487](https://github.com/taylorwilsdon/google_workspace_mcp/issues/487) (comment edit/delete) and
[#788](https://github.com/taylorwilsdon/google_workspace_mcp/issues/788) (Sheets cell anchoring).
`core/comments.py` still exposes create/reply/resolve only.

**Google's official server is now remote and documented, and still has no comments.** It is a
hosted endpoint at `https://drivemcp.googleapis.com/mcp/v1`, with a published MCP reference, and
exposes **exactly eight tools** — `copy_file`, `create_file`, `download_file_content`,
`get_file_metadata`, `get_file_permissions`, `list_recent_files`, `read_file_content`,
`search_files`. That confirms the count this project's README compares against, and the *remote*
part is a real architectural difference: theirs is a service, this is a local subprocess holding
your own OAuth client.

### Smaller entrants, listed so the survey is complete rather than flattering

`dbuxton/google-docs-mcp` (7★, Python, Apr 2026, no licence) · `phact/mcp-google-docs` (11★,
stale Feb 2025) · `stanislawherjan1/gdocs-comments-mcp` (3★, MIT) ·
`us-all/google-drive-mcp-server` (0★) · `asadudin/mcp-server-gdrive` (1★, stale). Hosted
platforms — Composio, Klavis AI, Pipedream, Zapier — wrap the same Drive API and expose
**file-level** comments only.

### What this survey does NOT claim

This project is **not** the broadest. `taylorwilsdon` covers 12+ Google services; `piotr-agier`
ships nearly three times the tools. Anyone wanting Gmail, Calendar, Slides authoring or Sheets
formatting should take one of those.

What remains only here, checked against each of the above rather than assumed: Sheets
comment→cell mapping (via XLSX export — the API cannot anchor one, see
`experiments/anchor-probe/`), the full comment lifecycle including **reopen**, `export_comments`
as a review register, the capability/allowlist policy layer with a flavour switch, and a stated
injection posture.

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

## Open discrepancy — RESOLVED (measured 2026-07-09)

`a-bonus`'s `commentAnchor.ts` parses a Sheets anchor shape `{ a: [{ sht: { sid, rng: {r, c} } }] }`, which raised the question of whether the read path is anchor-parseable after all. The [`anchor-probe`](../experiments/anchor-probe/) settled it against a live sheet: a UI-placed comment on B11 returns `{"type":"workbook-range","uid":0,"range":"1453957822"}` — **not** the `{a:[…]}` r/c shape. So:

- The read path is **not** anchor-parseable to A1: the real anchor's `range` is an opaque internal id. a-bonus's `{a:[…]}` parser does not match what real UI comments return (it likely only handles anchors it created itself, or is aspirational).
- The reference doc's XLSX-export conclusion **stands** and was confirmed (comments export to `xl/threadedComments/*.xml` with `ref="B11"`). Its "opaque" wording was corrected to "structured (`workbook-range`) but not A1-decodable." See [`google-drive-comments-reference.md` §7](./google-drive-comments-reference.md#7-the-anchor-field--the-hard-truth-for-sheets).

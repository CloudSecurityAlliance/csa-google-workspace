# Google Drive & Sheets Comments — API Reference & Behavior

> **Verified against Google Workspace documentation and primary sources in July 2026.**
> This document consolidates and supersedes the earlier `Google Drive API Comment-Related Capabilities.md`, `report-claude.md`, and `report-chatgpt.md`. See `../CHANGELOG.md` for what changed and why.

---

## TL;DR

1. **Comments live in the Google Drive API v3, not the Sheets API.** All comment/reply CRUD goes through `/drive/v3/files/{fileId}/comments`. The Sheets API cannot create, read, or delete comments.
2. **There are 10 methods total** — 5 on `comments`, 5 on `replies`. (An earlier draft claimed 12; there is **no `patch` method** in v3.)
3. **You cannot reliably anchor a comment to a specific Sheets cell via the API.** Google Workspace editors treat API-created anchors as *un-anchored*. This is the central, load-bearing limitation of the whole problem space.
4. **To map a comment back to an A1 cell, you must export the sheet as XLSX and parse the comment XML** — the Drive `anchor` field is opaque for Sheets and is not a usable read path.
5. **If you need text truly attached to a cell, use a Sheets *note* (Sheets API), not a comment.** Notes are genuinely cell-anchored; comments are file-level in practice.
6. `resolved` is read-only — resolve/reopen only by posting a **reply with an `action`**. Deletion is **soft**.

---

## 1. Which API handles what?

Google Sheets has **two distinct annotation systems**, and this is the root of most confusion:

| | **Notes** | **Comments** |
|---|---|---|
| What it is | Plain text stuck to a single cell (classic "Insert note") | Threaded discussion: replies, resolve/reopen, @mentions, author attribution |
| API | **Sheets API** — the cell's `note` field, set via `spreadsheets.batchUpdate` (`updateCells`/`repeatCell`) | **Drive API v3** — `comments` / `replies` resources |
| Genuinely cell-anchored? | **Yes** — anchoring is a property of the cell | **No** (file-level in practice; see §5) |
| Threading / resolution? | No | Yes |

**Rule of thumb:** need text reliably attached to a cell → *note*. Need a discussion thread with resolution → *comment* (and accept it will be file-level).

Sources: [Manage comments and replies](https://developers.google.com/workspace/drive/api/guides/manage-comments) · [Sheets API](https://developers.google.com/workspace/sheets/api)

---

## 2. Comments resource (Drive API v3)

Base path: `https://www.googleapis.com/drive/v3`
Reference: <https://developers.google.com/workspace/drive/api/reference/rest/v3/comments>

### Methods (5)

| Method | HTTP verb | Endpoint |
|--------|-----------|----------|
| `create` | POST | `/files/{fileId}/comments` |
| `get` | GET | `/files/{fileId}/comments/{commentId}` |
| `list` | GET | `/files/{fileId}/comments` |
| `update` | PATCH | `/files/{fileId}/comments/{commentId}` |
| `delete` | DELETE | `/files/{fileId}/comments/{commentId}` |

> There is **no `comments.patch`** in v3. `update` is the only body-mutating method and it uses the **PATCH** verb. `comments.patch` existed only in the legacy **v2** API.

### Comment resource fields

| Field | Type | Writable? |
|-------|------|-----------|
| `content` | string | **Yes** — plain text; required at create |
| `anchor` | string (JSON) | Settable at create; effectively immutable after (see §7) |
| `quotedFileContent` | object `{mimeType, value}` | Settable at create — the file content the comment refers to |
| `id`, `kind` (`drive#comment`) | string | No (output only) |
| `createdTime`, `modifiedTime` | RFC 3339 string | No |
| `author` | `User` object | No |
| `htmlContent` | string | No — server-rendered HTML for display |
| `resolved` | boolean | **No — output only** (see §4) |
| `deleted` | boolean | No |
| `replies[]` | array of `Reply` | No |

### `comments.list` parameters

| Parameter | Notes |
|-----------|-------|
| `pageToken` | Pagination cursor |
| `pageSize` | 1–100, default 20 |
| `startModifiedTime` | RFC 3339; minimum `modifiedTime` filter. **comments-only** (not on replies.list) |
| `includeDeleted` | Default false; deleted comments come back with content stripped |
| `fields` | **REQUIRED** — see box below |

> ⚠️ **`fields` is mandatory.** Google requires the `fields` parameter for *every* method of the `comments` and `replies` resources **except `delete`**. These methods return no default field set; omitting `fields` errors. Example: `fields="comments(id,content,author,resolved,anchor,replies),nextPageToken"`.
> Source: [fields parameter guide](https://developers.google.com/workspace/drive/api/guides/fields-parameter)

---

## 3. Replies resource (Drive API v3)

Reference: <https://developers.google.com/workspace/drive/api/reference/rest/v3/replies>

### Methods (5)

| Method | HTTP verb | Endpoint |
|--------|-----------|----------|
| `create` | POST | `/files/{fileId}/comments/{commentId}/replies` |
| `get` | GET | `/files/{fileId}/comments/{commentId}/replies/{replyId}` |
| `list` | GET | `/files/{fileId}/comments/{commentId}/replies` |
| `update` | PATCH | `/files/{fileId}/comments/{commentId}/replies/{replyId}` |
| `delete` | DELETE | `/files/{fileId}/comments/{commentId}/replies/{replyId}` |

### Reply resource fields

| Field | Type | Writable? |
|-------|------|-----------|
| `content` | string | **Yes** — required *unless* `action` is set |
| `action` | string | **Yes** — one of exactly `resolve` or `reopen` (see §4) |
| `id`, `kind` (`drive#reply`) | string | No |
| `createdTime`, `modifiedTime` | RFC 3339 string | No |
| `author` | `User` object | No |
| `htmlContent` | string | No |
| `deleted` | boolean | No |

`replies.list` supports `pageToken`, `pageSize`, `includeDeleted`, and requires `fields`. It does **not** support `startModifiedTime`.

---

## 4. Resolution model

`resolved` on a comment is **read-only**. You cannot set it via `comments.update`. A comment is resolved (or reopened) **only by creating a reply with an `action`**:

```jsonc
// POST /files/{fileId}/comments/{commentId}/replies?fields=id,action
{ "action": "resolve" }   // or "reopen"; content optional when action is set
```

Valid `action` values: **`resolve`**, **`reopen`** (exactly these two).
Source: [Manage comments and replies](https://developers.google.com/workspace/drive/api/guides/manage-comments)

> ⚠️ For **Sheets specifically**, resolution set via the API may not reliably reflect in the Sheets UI — this is part of the same anchoring/UI-sync gap described in §7.

---

## 5. Deletion model

Deletion is **soft** for both comments and replies. Drive marks the resource `deleted: true` and strips `content`/`htmlContent`; the record is retained to preserve thread structure. Only the author (or file owner, per permissions) may delete.

---

## 6. OAuth scopes

Comments are governed by the **standard Drive scopes** — there is no comment-specific scope:

| Scope | Use |
|-------|-----|
| `https://www.googleapis.com/auth/drive.readonly` | Read comments/replies |
| `https://www.googleapis.com/auth/drive.file` | Read/write on files the app created or the user opened with it (least-privilege for writes) |
| `https://www.googleapis.com/auth/drive` | Full Drive access |

> ❌ **`https://www.googleapis.com/auth/drive.comments` is not a real scope.** It appeared in an earlier draft (`report-claude.md`) and is incorrect. Use the scopes above.

Permission model: reading requires ≥ *reader*; creating comments/replies requires ≥ *commenter*; edit/delete is restricted to the author (or owner).

---

## 7. The `anchor` field — the hard truth for Sheets

This is the single most error-prone topic and the reason cell-precise comment tooling for Sheets is so hard.

### Official description
`anchor` is a **JSON string** that "defines a region in a file to which a comment refers." The only concrete worked example Google publishes is Docs-oriented:

```python
anchor = {"region": {"kind": "drive#commentRegion", "line": <n>, "rev": "head"}}
```

Google explicitly says developers "can define their own format for the anchor specification" — **and that when they do, "Google Workspace editor apps treat these comments as un-anchored comments."** Anchors are also immutable and "position relative to content cannot be guaranteed between revisions."
Source: [Manage comments and replies](https://developers.google.com/workspace/drive/api/guides/manage-comments)

### What this means for Sheets (CONFIRMED)
- **Writing a cell anchor doesn't work.** A comment created via the Drive API with an anchor targeting a cell (e.g. `AW437`) lands as a **file-level, unanchored** comment in the Sheets UI. @mentions still notify correctly; the comment is simply not tied to the cell. Corroborated by [Pipedream #18185](https://github.com/PipedreamHQ/pipedream/issues/18185) (marked *blocked*) and the [a-bonus/google-docs-mcp](https://github.com/a-bonus/google-docs-mcp) README ("Google Workspace editors treat Drive API anchors as unanchored comments").
- **No Sheets-specific anchor structure is documented anywhere** in the public API surface.

### Reading a comment's cell is a *different* mechanism (CONFIRMED)
The Drive `anchor` is **not** a usable read path for Sheets either. The reliable, ecosystem-proven way to answer "which cell is this comment on?" is:

1. **Export** the spreadsheet as XLSX: `GET /drive/v3/files/{spreadsheetId}/export?mimeType=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
2. **Unzip** and parse the Office Open XML comment parts (`xl/comments*.xml` + worksheet XML), where each comment is stored against a **cell `ref` in A1 notation**.
3. Map to a clean result, e.g. `{"range": {"a1Notation": "B11", "row": 11, "col": 2}, "comment": [...]}`.

This is exactly what tanaikech's [DocsServiceApp](https://github.com/tanaikech/DocsServiceApp) does; its docs state plainly that "there are no methods for retrieving the comments with the cell coordinate in the existing Google Spreadsheet service and Sheets API." See also the community thread [How to map Google Sheet Comments to an A1 range](https://support.google.com/docs/thread/234205749).

### ⚠️ Debunked folklore
The formats below circulated in earlier drafts of this repo. **No primary source produces them as real Drive API Sheets anchors. Do not rely on them:**
- `R1C2` as a comment anchor — *R1C1 is real, but as Sheets API **range** notation (`Sheet1!R1C1:R2C2`), not a comment anchor.*
- `sheet_id=123456&range=A1` query-style anchors — no source.
- `{"a":[{"type":"cell_classifier","row":N,"column":N}]}` / `range_classifier` / `workbook-range` JSON — no source; these were self-flagged as "requires reverse engineering" in the original doc, i.e. hypotheses.
- `anchor=kix.XXXX` — `kix` is the **Google Docs** editor's internal namespace, not Sheets.

Bottom line: **real Sheets comment anchors are opaque.** Treat the anchor as unusable for Sheets in both directions.

Tracker references (behavior confirmed; exact current status is sign-in-gated and unverified): [#292610078](https://issuetracker.google.com/issues/292610078), [#357985444](https://issuetracker.google.com/issues/357985444).

---

## 8. Practical workarounds

Three real, ecosystem-used patterns:

1. **Embed a clickable cell hyperlink in the comment body.** The comment stays file-level, but readers can click through to the target cell (a-bonus's `createSheetsComment` with `includeCellLink=true`).
2. **Use a native Sheets *note* when text must live on the cell** — written via the Sheets API `note` field. Notes are truly cell-attached.
3. **Read side: export-as-XLSX and parse comment XML** to recover A1 positions (§7).

---

## 9. File-type support notes
- **Anchored comments** are supported for Google Workspace editor files *in principle* (Docs honors text-range anchors better than Sheets does).
- **Blob (non-Google) files** support **unanchored comments only**.
- Sheets is the problematic case: anchors are accepted by the API but not honored by the editor.

---

## 10. Sources
- [Drive API v3 — comments resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/comments)
- [Drive API v3 — replies resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/replies)
- [Manage comments and replies (guide)](https://developers.google.com/workspace/drive/api/guides/manage-comments)
- [The `fields` parameter (guide)](https://developers.google.com/workspace/drive/api/guides/fields-parameter)
- [Drive API v3 vs v2](https://developers.google.com/workspace/drive/api/guides/v3versusv2)
- [tanaikech/DocsServiceApp](https://github.com/tanaikech/DocsServiceApp) (XLSX-export read technique)
- [Pipedream #18185](https://github.com/PipedreamHQ/pipedream/issues/18185) · [a-bonus/google-docs-mcp](https://github.com/a-bonus/google-docs-mcp)
- Issue Tracker [#292610078](https://issuetracker.google.com/issues/292610078), [#357985444](https://issuetracker.google.com/issues/357985444)

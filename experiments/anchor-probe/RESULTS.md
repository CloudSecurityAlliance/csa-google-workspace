# Anchor Probe — Results (run 2026-07-09)

Ran `probe.py --all` against a live throwaway Google Sheet (owner `kseifried@cloudsecurityalliance.org`). Raw, unedited findings below. These drove the corrections in [`../../research/google-drive-comments-reference.md` §7](../../research/google-drive-comments-reference.md).

## Test B — raw anchor of a UI-placed comment (the decisive datum)
A comment placed on cell **B11** via the Sheets UI returned, from `comments.list`:

```json
{"type":"workbook-range","uid":0,"range":"1453957822"}
```

**Finding:** the anchor is **structured** (format `workbook-range`), *not* opaque/absent as previously stated. **But** `range` is an opaque internal id (not `B11`, not row/col) and `uid` is a sheet index — so the anchor is **not A1-decodable**. `quotedFileContent` was `null`.

## Test A — creating a comment with a cell anchor
Sent: `{"r":"head","a":[{"sht":{"sid":0,"rng":{"r":10,"c":1}}}]}` (targeting B11).
- The Drive API **stored our JSON verbatim** in the `anchor` field.
- In the XLSX export, that comment appeared on **A1**, not B11.

**Finding:** custom/API anchors are ignored by the editor for placement → effectively unanchored. **Write-side cell anchoring confirmed impossible.**

## Test C — XLSX export
Comments export into **two** parts, both with A1 `ref`s:
- `xl/threadedComments/threadedComment1.xml` — the modern threaded-comments part (`<threadedComment ref="B11" …>`)
- `xl/comments1.xml` — legacy mirror for Excel compatibility

A1 refs recovered: `['B11', 'A1']` (B11 = the UI comment; A1 = our API-created one).

**Finding:** the **XLSX-export read path works** and yields real A1 references — the mapping the Drive `anchor` field does not provide. Sheets comments are *threaded comments*.

## Threads / reply history (re-run 2026-07-09 with reply subfields)
The B11 comment's full thread is accessible both ways:

- **Native Drive API** — `comments.list` with expanded `replies(author(displayName),content,createdTime,action,deleted)` returns replies in chronological order with author + timestamp:
  ```
  comment AAAB_oJ0OTY (B11), 2 replies:
    2026-07-10T04:23:50Z Kurt Seifried: yo, herte's a reply
    2026-07-10T04:24:03Z Kurt Seifried: @kurt@seifried.org see this?
  ```
  (Replies **must** be requested with subfields — `replies` alone returns them empty.)
- **XLSX export** — `xl/threadedComments/threadedComment1.xml` links replies to the root via `parentId`, all on `ref="B11"`; legacy `xl/comments1.xml` flattens the thread into one `Comment:/Reply:/Reply:` text blob.

**Findings:** full thread history (author, timestamp, and `resolve`/`reopen` action per reply) is available via the API `replies` array. **@mentions are stored as plain text** in `content` (`@kurt@seifried.org see this?`) — no structured mention object.

## Net effect on the research
- Corrected "anchors are opaque" → "structured (`workbook-range`) but not A1-decodable."
- Moved `workbook-range` out of the "folklore" list — it is the real format.
- Confirmed (not just documented) both the write limitation and the XLSX read path.
- Resolved the a-bonus `{a:[…]}` discrepancy: that shape is not what real UI comments carry.

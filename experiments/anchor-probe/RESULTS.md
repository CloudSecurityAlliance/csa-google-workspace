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

## Net effect on the research
- Corrected "anchors are opaque" → "structured (`workbook-range`) but not A1-decodable."
- Moved `workbook-range` out of the "folklore" list — it is the real format.
- Confirmed (not just documented) both the write limitation and the XLSX read path.
- Resolved the a-bonus `{a:[…]}` discrepancy: that shape is not what real UI comments carry.

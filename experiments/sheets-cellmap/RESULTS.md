# Sheets Cell-Mapping Probe — Results (run 2026-07-22)

Ran `probe_cellmap.py` to nail the **real** XLSX comment structure the Phase-4
cell-mapper must parse, and to get an export-size data point. Throwaway Sheet with
API-created comments (they land file-level/A1 but still export into the comment XML,
so the *structure* is identical to UI comments — only the `ref` cell differs). Raw findings below.

## The three comment parts in an exported XLSX

**`xl/threadedComments/threadedComment1.xml`** — the modern part, one per worksheet (`threadedComment2.xml` for the 2nd tab, etc.). Namespace `http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments`:
```xml
<x18tc:threadedComment ref="A1" dT="2026-07-22T00:24:47.00"
    personId="{8631b593-…}" id="{90fb754f-…}" done="0">
  <x18tc:text xml:space="preserve">East looks high</x18tc:text>
</x18tc:threadedComment>
<x18tc:threadedComment ref="A1" dT="2026-07-22T00:24:46.00"
    personId="{8631b593-…}" id="{edae2415-…}" parentId="{99d453d5-…}">
  <x18tc:text xml:space="preserve">checking now</x18tc:text>   <!-- a reply: has parentId -->
</x18tc:threadedComment>
```
- `ref` = **the cell in A1 notation** (what we want).
- `id` = a **GUID unrelated to the Drive comment id** — so we CANNOT match on id.
- `parentId` present ⇒ this is a reply; root comments have no `parentId`.
- `dT` = timestamp, **second precision, no timezone** (`…47.00`).
- `done="0"` = unresolved (present on roots).

**`xl/persons/person.xml`** — maps `personId → displayName`:
```xml
<x18tc:person displayName="Kurt Seifried" id="{8631b593-…}" providerId="google-sheets"/>
```

**`xl/comments1.xml`** — legacy Excel-compat mirror (flattened `[Threaded comment]… Comment:… Reply:…` text, also `ref="A1"`). The parser should prefer the threaded part and ignore this.

## The matching key (decisive for the mapper)
Because the XLSX `id` is unrelated to the Drive comment id, matching a Drive comment to its cell must join on:
- **author displayName** (Drive `author.displayName` == persons.xml `displayName` via `personId`), **and**
- **text** (Drive `content` == threadedComment `<text>`), **and**
- **timestamp** — but normalize: XLSX `dT` is second-precision & zoneless (`2026-07-22T00:24:47.00`) while Drive `createdTime` is millisecond + `Z` (`2026-07-22T00:24:47.079Z`). **Match at whole-second granularity, treating `dT` as UTC.**

Only **root** threadedComments (no `parentId`) are candidates. If two roots share `(displayName, text, second)`, the match is **ambiguous → yield `location=None`** (never a wrong guess). This confirms the caveat in [`../../research/google-drive-comments-reference.md` §7].

## Export size vs the ~10 MB cap
An **8000×15 (120k-cell)** sheet exported to XLSX in **0.69 MB**. Google's `files.export` cap (~10 MB) is generous — typical comment-bearing sheets won't approach it. The mapper needs only a graceful `try/except → location=None` on export failure, not elaborate cap handling.

## Net effect on the design
- Parser targets `xl/threadedComments/*.xml` + `xl/persons/*.xml`; namespace-agnostic tag matching (strip `{ns}`), since the MS namespace is verbose and stable-ish.
- Match key = (displayName, content, whole-second UTC timestamp); ambiguous/no-match → `None`.
- Export-cap handling is a simple guarded degrade, not a first-class concern.

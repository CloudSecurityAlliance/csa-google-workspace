# Docs Suggestions Probe — Results (run 2026-07-20)

Ran `probe_suggestions.py` against a live Google Doc that `kurt@seifried.org`
prepared in **Suggesting mode** (one suggested insertion + two comments), while
authenticated as `kseifried@cloudsecurityalliance.org`. This settles whether
"suggesting mode" edits are reachable via the API. Raw findings below.

> **Setup note (itself a finding):** a freshly-scoped OAuth token still returned
> `403 SERVICE_DISABLED` until the **Google Docs API** was enabled in the Cloud
> project. Scope grant ≠ API enablement — they are two separate switches. The
> library's error handling should detect `reason: SERVICE_DISABLED` and name the
> API + activation URL.

## S1 — reading suggestions WORKS (but one suggestion spans many runs)
With `suggestionsViewMode=SUGGESTIONS_INLINE`, suggested text arrives as text runs
carrying `suggestedInsertionIds` (or `suggestedDeletionIds`). The single inserted
sentence appeared as **4 runs all sharing one id** `suggest.n8flcabn9nz6`:
```json
{"text":"This is a suggested edit from ","kind":"insertion",
 "suggestedInsertionIds":["suggest.n8flcabn9nz6"]}
```
**Reconstructing one logical suggestion means grouping runs by suggestion id.**

## S2 — the three view-modes behave as documented (read-only accept/reject preview)
- `SUGGESTIONS_INLINE` → text **including** the suggestion.
- `PREVIEW_SUGGESTIONS_ACCEPTED` → text **as if accepted** (insertion present).
- `PREVIEW_WITHOUT_SUGGESTIONS` → text **as if rejected** (insertion absent).

So we can compute "what the doc looks like accepted vs rejected" with **read-only**
calls — a real capability (`doc.text(suggestions="accepted"|"rejected"|"inline")`).

## S3 — suggestion AUTHOR / timestamp are NOT exposed
The suggested runs carried no author or time (`other_keys` was empty aside from
`suggestedTextStyleChanges`), and the document object's top-level keys were only:
`body, documentId, documentStyle, namedStyles, revisionId, suggestionsViewMode, title`
— **no suggestion registry**. **`Suggestion.author` is impossible via the Docs API.**

## S4 — DECISIVE: there is NO accept/reject endpoint
Enumerated the entire Docs API surface from the discovery document:
- `documents.*` methods: **`create`, `get`, `batchUpdate`** (three, none suggestion-related).
- `batchUpdate` Request types: **40 total** — `insertText`, `deleteContentRange`,
  `replaceAllText`, … — **zero** contain "suggest", "accept", or "reject".

```
"suggestion_related_request_types": []
"accept_or_reject_methods": []
"VERDICT": "NO accept/reject endpoint exists"
```
**Accepting or rejecting a suggestion is not possible through the Docs API.** There
is no clean workaround either: API edits are always direct (non-suggesting), so you
cannot "promote" a suggestion to permanent text, and you cannot delete a suggestion.
This is **Playwright-only territory** (drive the real UI) for the future.

## S5 — Docs comments work like Sheets, and anchor BETTER
Reading the doc's Drive comments returned normal threads, with two Docs-specific wins:
```json
{"id":"AAACDmsEG-Q","content":"This is a comment about the first part of my suggestion",
 "anchor":"kix.nhqmp3maw4gt",
 "quotedFileContent":{"mimeType":"text/html","value":"This is a suggested"},
 "author":{"displayName":"Kurt Seifried","me":false}}
```
- Docs anchors are the **`kix.*`** namespace (not Sheets' `workbook-range`).
- **`quotedFileContent` is populated** — the anchored text comes back directly, so
  Docs comment→location mapping is trivial (unlike Sheets, which needs XLSX export).
- **`me:false`** here — correct: the *author* is `kurt@seifried.org` but we authed as
  `kseifried@cloudsecurityalliance.org`. `me` reliably distinguishes the two identities.

## Not tested
- **Suggested *deletions*.** The fixture had only an insertion. The mechanism is
  symmetric (`suggestedDeletionIds`) but is empirically **unconfirmed** here.

## Net effect on the design
- Suggestions ship **read-only**: list suggestions (grouped by id) + accepted/rejected
  text previews. **Drop** `Suggestion.author` (unavailable) and any `apply_as_edit()`
  "accept" (no such capability exists — verified by full API enumeration).
- Docs comments get **reliable `quoted_text`**; Sheets remains the hard mapping case.
- New library requirement: classify `403 SERVICE_DISABLED` and tell the user which
  API to enable.

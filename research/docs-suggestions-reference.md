# Google Docs Suggestions — API Reference & Behavior

> **Empirically measured 2026-07-20** via [`experiments/docs-suggestions`](../experiments/docs-suggestions/).
> "Suggesting mode" edits are a *different* system from comments; this documents what
> the Docs API can and cannot do with them. See `../CHANGELOG.md` for history.

---

## TL;DR

1. **Suggestions ≠ comments.** A "suggestion" is a tracked edit (insert/delete) made in
   Docs **Suggesting mode**. Comments are the Drive-API threads (see
   [`google-drive-comments-reference.md`](./google-drive-comments-reference.md)). A doc can have both.
2. **You can READ suggestions** via the Docs API v1 (`documents.get`) — they surface as
   `suggestedInsertionIds` / `suggestedDeletionIds` on text runs.
3. **You CANNOT accept or reject a suggestion via the API.** Enumerating the entire Docs
   API surface (3 methods, 40 `batchUpdate` request types) turns up **zero** suggestion
   operations. This is a hard ceiling, confirmed by measurement, not documentation.
4. **Suggestion authorship/timestamp is not exposed** — there is no way to say *who*
   suggested an edit or *when* through the API.
5. **Suggestions can only be created in the UI** — there is no API to author one.
6. Only **Google Docs** has this system in a Docs-API-readable form. (Sheets/Slides have
   their own review flows; not covered here.)

---

## 1. Reading suggestions

`documents.get` takes a `suggestionsViewMode`:

| `suggestionsViewMode` | Returns |
|-----------------------|---------|
| `SUGGESTIONS_INLINE` (default) | Full content **including** suggestions, each marked on its text runs |
| `PREVIEW_SUGGESTIONS_ACCEPTED` | Content **as if every suggestion were accepted** |
| `PREVIEW_WITHOUT_SUGGESTIONS` | Content **as if every suggestion were rejected** |

The two PREVIEW modes are how you compute "accepted vs rejected text" **read-only** —
no mutation, and no accept/reject endpoint required.

### Structure (measured)
A suggested insertion appears as one or more text runs carrying a shared id:
```json
{ "textRun": { "content": "This is a suggested edit from ",
               "suggestedInsertionIds": ["suggest.n8flcabn9nz6"] } }
```
- **One logical suggestion can span multiple runs** (styling boundaries split it). To
  reconstruct a suggestion, **group runs by suggestion id**.
- Deletions use `suggestedDeletionIds` on the runs being removed. *(Insertion was measured
  directly; deletion is symmetric per the schema but was not exercised in the probe.)*
- **No author or timestamp** is attached to a run or exposed at the document level. The
  document object's only top-level keys are `body, documentId, documentStyle, namedStyles,
  revisionId, suggestionsViewMode, title`.

---

## 2. Accepting / rejecting — not available

`documents.batchUpdate` is the only mutating method. Its **40** request types cover text,
tables, styles, headers/footers, named ranges, images, etc. — and **none** accept, reject,
or otherwise resolve a suggestion. There is no `documents.acceptSuggestion` method.

There is also **no clean workaround**:
- API `insertText`/`replaceAllText` edits are always **direct** (non-suggesting), so you
  cannot "promote" an existing suggestion into permanent text — you'd only add duplicate content.
- You cannot delete a suggestion via the API either.

**Accept/reject is achievable only by driving the Docs UI** (e.g. a future Playwright-based
backend). Treat it as out of scope for any API-only implementation.

---

## 3. Implications for a comments/review library

- Expose suggestions **read-only**: enumerate them (grouped by id, with `kind` =
  insertion/deletion and the affected text), and offer accepted/rejected **text previews**
  via the two PREVIEW view-modes.
- **Do not model a `Suggestion.author`** — it cannot be populated.
- **Do not offer an "accept"/"reject" method** on an API-only backend. If offered later,
  it must be a UI-automation backend, clearly labeled.
- Reading requires the `documents`/`documents.readonly` scope **and** the Google Docs API
  enabled in the Cloud project (a scoped token alone returns `403 SERVICE_DISABLED`).

---

## 4. Sources
- [Docs API — `documents.get` / `suggestionsViewMode`](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/get)
- [Docs API — `Request` (batchUpdate) types](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/request)
- Measured: [`experiments/docs-suggestions/RESULTS.md`](../experiments/docs-suggestions/RESULTS.md)

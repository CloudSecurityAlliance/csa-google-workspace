# Comment Lifecycle Probe — Results (run 2026-07-20)

Ran `probe_lifecycle.py` against a **self-created throwaway Google Sheet** (owner
`kseifried@cloudsecurityalliance.org`), exercising the full comment/reply cycle
and capturing raw `comments`/`replies` responses. Fixture trashed afterward. Raw,
unedited findings below; these validate the comment-surface design and corrected
two assumptions before they became bugs.

## Q1 — `resolved` is ABSENT on a fresh comment (not `false`)
`comments.create` returned **no `resolved` key at all**:
```json
{"id":"AAACDlbyg7c","content":"probe comment ONE","deleted":false,
 "author":{"displayName":"Kurt Seifried","me":true},
 "createdTime":"2026-07-20T23:05:59.479Z","replies":[]}
```
The `resolved` field only appears **after a resolve/reopen action has ever occurred**
on the thread. **Consumers must treat a missing `resolved` as `False`** — a naive
`comment["resolved"]` KeyErrors on every never-resolved comment (the common case).
`anchor` and `quotedFileContent` are likewise omitted when empty.

## Q2 — `author.me` exists; `emailAddress` is withheld even when requested
Author came back as `{"displayName":"Kurt Seifried","me":true}`. We **explicitly
requested `author(...,emailAddress)` and Google did not return it** — confirming
`emailAddress` is frequently unavailable by design. `me:true` here (we authored it).

## Q3 / Q4 — resolve works as an action-reply, and can be CONTENT-LESS
`replies.create` with body `{"action":"resolve"}` and **no content** was accepted:
```json
{"id":"AAACDlbyg7k","content":"","action":"resolve","deleted":false}
```
A subsequent `comments.get` then showed **`resolved: true`**. So `.resolve()` /
`.reopen()` need not force reply text.

## Q5 — reopen flips it back
`{"action":"reopen"}` (also content-less) → `comments.get` shows **`resolved: false`**.
The full `replies` array retains the resolve *and* reopen actions in order — the
audit trail.

## Q6 — editing our own comment and reply works
`comments.update` (new `content`, bumped `modifiedTime`) and `replies.update` both
succeeded on our own content. (Editing another user's comment was not tested; the
API restricts it to the author and is expected to 403.)

## Q7 — delete is soft AND strips author + content
After `comments.delete` (returns 204, no body):
- `comments.list` **default (`includeDeleted=false`)** → **empty**; the comment is gone.
- `comments.list` **`includeDeleted=true`** → the comment is present but reduced to:
  ```json
  {"id":"AAACDlbyg7c","deleted":true,
   "createdTime":"...","modifiedTime":"...",
   "replies":[{"id":"...","deleted":true,"htmlContent":""}, ...]}
  ```
  **No `content`, no `author`, no `resolved`.** All replies also flip `deleted:true`
  with content cleared. **A deleted `Comment` must tolerate absent author/content.**

## Net effect on the design
- Comment surface (`.reply()` / `.resolve()` / `.reopen()` / `.edit()` / `.delete()`)
  validated end-to-end against the live API — the action-reply mechanic, content-less
  actions, and soft delete all behave as designed.
- **Two corrections captured in the reference doc:** `resolved` is *absent* (not `false`)
  until first resolved; delete strips *author* too (the reference previously said only
  content/htmlContent). See `research/google-drive-comments-reference.md` §2, §5.

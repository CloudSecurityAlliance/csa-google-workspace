# `google-workspace-api-specimens` — the public specimen corpus

**Drive:** `CSA-CINO-Public-Artifacts` · **Folder:** `google-workspace-api-specimens/comments`
Built 2026-09-03 by [`build.py`](build.py). Ids in [`manifest.json`](manifest.json).

Serves [#388](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/388) and the
comments reference ([#340](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/340)).

## What this is

Files that exhibit specific, **measured** behaviours of the Google Workspace APIs, so a claim in
the reference can be *checked* rather than taken on trust. Open the file, look at the sidebar,
see the thing.

**Every file documents itself.** Its content says what it is, which finding it evidences, what to
look at, **how it was made**, and what a human still has to place by hand. There is no separate
key to hold, and the documentation cannot drift from the fixture because it **is** the fixture.

## Why it had to exist

Every finding in this repository came from a document somebody built **by hand** — only the
editor mints a real anchor, only a human can select nothing and comment, only a human can comment
on an image. **And every one of those documents was trashed after use.**
`experiments/docs-anchor-states/` and `experiments/api-created-comment-states/` each rebuilt the
same numbered-paragraph fixture from scratch.

## Specimens

| file | what it holds |
|---|---|
| `README - what this folder is` | folder-level orientation, in the top folder |
| `docs-anchor-states` | the four attachment states, incl. `quote_only` — which only the API can make |
| `docs-sloppy-selections` | a one-word quote occurring four times, a quote spanning a paragraph, a three-word quote of a long paragraph |
| `docs-structure` | a heading, a table, and an empty paragraph the editor **refuses** to comment on |
| `docs-lifecycle` | resolved, reopened, soft-deleted, and a content-less action reply |

Still to build (they need a browser, a second account, or both — see
`research/comments-knowledge-map.md`): `docs-suggestions`, `docs-tabs`, `sheets-cell-mapping`,
`sheets-header-not-row-1`.

**`slides-comments` is DONE** (2026-09-05). Six comments placed through the editor on every kind
of target a deck has — the slide, a shape, text inside that shape, a shape with no text, a table
cell and the speaker notes — and the raw anchors read back. It is the specimen that changed a
belief rather than confirming one: a Slides anchor is **readable**, where Docs and Sheets anchors
are opaque. Findings in [`../slides-anchors/RESULTS.md`](../slides-anchors/RESULTS.md), and the
deck's own README slides say the same thing to anyone who opens the link.

Two things about that file differ from every other specimen, both forced rather than chosen:

* **its documentation is on README SLIDES, not in a file-level comment** — Drive caps comment
  content at **4096 UTF-8 bytes** (measured 2026-09-05; the library now raises `InvalidInputError`
  for it instead of letting a 403 masquerade as a permission problem) and the text is 4972;
* **it is paginated across three slides**, because a slide is a fixed canvas and Slides does not
  clip overflow — it draws it outside the slide, so one long README *looks* right in the editor
  and silently loses its last third in presentation and thumbnail views.

**`docs-structure` could not be used the way it told you to, until 2026-09-08.** It asked for a
comment on a heading and a comment on a table cell, and the document contained **neither** —
"Section Two" was `NORMAL_TEXT` and there were **zero** tables in it. The builder only ever
styled the section headings and never created structural material. Found by trying to follow the
instructions.

Two rules came out of fixing it, and both are general:

* **Material that a rule is about has to BE that structure**, not prose describing it. A
  specimen for headings and tables needs a real `HEADING_2` and a real table, or the rule it
  exists to exercise cannot be exercised.
* **An instruction must never quote the material verbatim.** The line
  *"Comment on the heading 'Section Two' below"* put that string in the document **twice**, so a
  comment on the real heading came back `ambiguous` — a Docs anchor carries no position, and
  quoted text is the only way to locate one. The instruction destroyed the uniqueness the
  material exists to provide. Refer to material by its **role**.

## What the script can and cannot do

It places the comments **only the API can make** — file-level, and quote-only. Everything else
needs a human in the editor, because an API-supplied anchor is stored verbatim and then treated
as un-anchored.

Each file therefore carries its **own** outstanding hand-placement under *"STILL TO BE PLACED BY
HAND"*, so the instructions travel with the specimen rather than living in a script nobody reads
twice.

## Three comments on every specimen, labelled A, B and C

Deliberately, and the labels are load-bearing — a reader has to be able to tell an API-created
comment from an editor-created one, because the difference is the finding:

- **A** — file-level: no anchor, no quoted text.
- **B** — quote-only, quoting text that **is** in the document. An honest quote with no anchor.
- **C** — quote-only, quoting text that is **not in the document at all**. Drive validates that
  field against nothing (#380), so a comment can attribute words to a document that never
  contained them. Sitting next to B, the pair shows that the API cannot tell them apart.

All three render as *"Original content deleted"* with no quoted text shown and no marker in the
body, and are filtered from the editor's default sidebar view. **That is the specimen working.**

## Rules

- **Everything synthetic.** Public, permanently, indexable. No real content, ever.
- **Cited by id.** Renaming and moving are safe — a Drive file id survives both. **Deleting
  breaks the citation**, and **copying produces a new id nothing cites** (and drops every
  comment, which is itself a finding).
- **Do not tidy this folder.**
- Re-running `build.py` is safe: files are matched by name and reused. `--rewrite` replaces a
  body, which **shifts every character index and breaks every hand-placed anchor** on that file.
  That is the one destructive option and it is opt-in.

## Not yet public

The drive carried `driveMembersOnly: true` when the folder was made, so an `anyone:reader`
permission was **refused** (400). The org itself permits link sharing — measured separately on a
My Drive file — so the drive-level restriction is the blocker, and lifting it is a drive-wide
decision for its organizer rather than something this tooling should do.

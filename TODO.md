# TODO / backlog

> ## ⏰ ROTATE `CONTROLS_TOKEN` ON OR BEFORE **2027-09-01**
>
> The fine-grained PAT behind the weekly external-controls check
> (`.github/workflows/controls.yml`) **expires 2027-09-01 04:12:36 UTC** — 366 days from
> 2026-08-31, which is GitHub's maximum. Nothing in this repository knows that date, and
> nothing will warn you: when it lapses the branch-protection control silently reverts to
> **UNVERIFIABLE**, which is the honest state and an invisible one.
>
> **Replace it with:** a fine-grained PAT, resource owner `CloudSecurityAlliance`, **only**
> the `csa-google-workspace` repository, **Repository permissions → Administration:
> Read-only** and *nothing else* (metadata read comes along automatically). Then
> `gh secret set CONTROLS_TOKEN`.
>
> **Verify the replacement before trusting it**, because the first attempt was
> over-permissioned and it was not obvious: `GET /repos/{owner}/{repo}`'s `permissions`
> object is **not** evidence — it reports the *user's* org role, not the token's grants, and
> reads `admin: true` for a correctly-scoped token. The real test is a write that must fail:
> `PATCH /issues/{n}` with the state it already has should return **403 "Resource not
> accessible by personal access token"**, while
> `GET /branches/main/protection` returns **200**.


The feature roadmap (comments · content read/write · Sheets cell-mapping · Docs
suggestions read) is **complete and live-verified** — see `CHANGELOG.md`. This file
is the post-roadmap backlog: the phase-2 delivery layer (below), plus enhancements and
polish to the library itself (comments + content on Google Docs/Sheets/Slides), none of
the latter blocking.

Ordered by leverage-to-effort. Nothing here is committed to — it's a menu. Each item,
when picked up, follows the plan-then-execute rhythm (spec/plan under
`docs/superpowers/`, then TDD via `FakeBackend`). `CHANGELOG.md` is the shipped-work
ledger; the phase plans in `docs/superpowers/plans/` are the per-phase detail.

## The current plan — five waves, agreed 2026-09-01

Twenty-nine issues were open after v0.39.0, and they are **not twenty-nine problems**. Roughly a
third are one recurring defect, six orbit the threat model, five are small real bugs, and four are
the only group that adds capability. This section is the order to work them in and, more usefully,
*why that order* — the dependency arguments are the part that would be expensive to re-derive.

Ordering principle: **what removes future work**, not what looks most alarming. Both audits of
2026-09-01 found **0 exploitable** issues, so nothing here is a race.

### Wave 1 — adopt the re-scored threat model · `0.39.1`

Issues: **#310** (anchor), then #318, #331, #317, #328, most of #309.

The register is **already written** — 251 lines, 43 threats, 25 entry points, frozen in
`docs/security-audits/2026-09-01-defending-code-reference-harness-claude/THREAT_MODEL.md`. Adopting
is review-and-promote, not authoring, which is what makes this cheap enough to go first.

**Why first, and it is not severity.** #317 and #318 are guards *on* the threat model. Fix them
before adopting the new register and you do them twice.

It removes an actively false claim: **T20 reads `mitigated` on a control that no longer exists.**

Two things found while checking, both of which must happen *before* the promotion:

1. **#318 first.** `test_threat_model.py` bounds §4 by *column count*, not section membership, so it
   parses a §0 row as a §4 threat. Promoting while that holds means the adoption is validated by a
   parser that miscounts — and the count is the thing being changed.
2. **#331 next.** The frozen register's header and every provenance cell credit audit
   `2026-09-01-01`, but the record was renumbered `-02` when the two same-day audits collided.
   Promote as-is and the living register inherits wrong attribution — and provenance is the entire
   point of §0b.

**The snapshot is already one day stale**, frozen at `d33034b`/v0.38.0 while we are at v0.39.0 with
five of its findings fixed — T8 still says *"tool DESCRIPTIONS are not guarded"*, which #332 made
false. So adoption is **not** a copy: it needs a new §0 recording what moved since the freeze. That
is the judgement-heavy step and the one that cannot be mechanised; it is also exactly what §0 is
for.

Then: repoint the test's baseline, reset §0b, `SECURITY.md` 36 → 43 threats and 19 → 25 entry
points, and #317 so those counts cannot drift again (`FROZEN_COUNTS = {"THREAT_MODEL.md"}` is dead
code today because the file never enters the loop it would filter).

**Why the immutability property survives:** the register being promoted was authored by an
*independent audit*, not by us. Moving the baseline to a newer independent snapshot keeps
"a status cannot quietly improve" intact; rewriting it ourselves would not.

### Wave 2 — the recurring defect, as one campaign · `0.39.2`

Issues: #319, #321, #322, #323, #324, #325.

All one shape: **a hand-maintained list that fell behind what it guards.** Three instances were
already fixed on 2026-09-01 (#308, #320, #332), and two audits found eight more in a single day.
Fixing instances is losing.

So this wave fixes the six *and* adds one meta-check that flags a hand-maintained collection which
has fallen behind a derivable source. That converts a class into a solved problem; otherwise the
next audit files six more of the same.

The general technique, learned in #320 and worth reusing: **self-test the detector.** A guard whose
input can legitimately be empty cannot be repaired by asserting the input is non-empty — that
forces drift-prone content into prose. Run the detector against synthetic input instead.

### Wave 3 — the five small real bugs · `0.40.0`, deliberately not a patch

Issues: #313, #314, #315, #326, #327, plus #334 (lockfiles) and #348.

- **#313** tab titles into a client cache this server cannot rotate or purge — defeats the
  "operation, never content" rule honoured everywhere else.
- **#314** a filesystem existence oracle that leaks *when the local-read switch is off*, i.e. inside
  the switch whose stated purpose is removing local exposure.
- **#327** `has_write_scope` is an allowlist of four known write scopes, so `drive.file` — a write
  scope this project does not request — passes the read-only check. Invert to a subset test.
- **#326** `openWorldHint` on a server whose entire read surface returns third-party content.
- **#315** a default install is told nothing about capabilities, so the operator hears about the two
  axes that were always open and not the one that changed in v0.31.0.

**A minor, not a patch**, even though it is audit remediation: #326 adds annotations, #315 changes
startup output, and #327 can newly *refuse* a token that previously passed. All caller-observable.
Better to bump the minor than ship a behaviour change as a patch.

### Wave 3.5 — the account axis: work-handoff inventory · `0.41.0`

Spec: `docs/superpowers/specs/2026-09-02-work-handoff-inventory.md`. Tracking: #350.

Added 2026-09-02 from a real need: somebody unavailable for a month, a question that cannot wait,
and *"where is their work and what is in it?"* Enumerate every file a person edited or commented
on over a year or two, into a dated Sheet a colleague can work through.

**This reorders #338.** It was an enhancement; it is now a **correctness dependency** — an
inventory that cannot say which shared drive a file lives in will silently mis-attribute or omit
work, which is worse than not offering the feature.

Prerequisites, all small and all previously filed as search polish:

- **#338** — `driveId` unreported (blocking, see above)
- `owners`, `createdTime`, `lastModifyingUser` in `_SEARCH_FIELDS` — five fields are requested
  today, so an inventory would spend an extra call per file on facts Drive returns for free
- `orderBy` beyond its three descending keys — `createdTime` is filterable but not sortable

**Why this is not the caching decision reopening.** That decision was reasoned from the live
multi-reviewer case, where staleness lands in exactly the sessions this tool is for. A handoff
inventory is the inverse: the subject is not editing, so a frozen view is *correct* and should not
drift while somebody works through it. The snapshot is a **deliverable** — a dated Sheet, the same
shape `export_comments` already ships — and it is **never an access path**.

**The seam that matters, and it is drawn by PRINCIPAL rather than by question** (refined
2026-09-02): *this server does only what the Drive and Docs APIs support and runs AS A USER;
administrators use the separate Google audit MCP server.* So the inventory must accept **a list of
file ids** as an input mode and not only a Drive query — an administrator produces the list there,
this runs as a user against it — and `driveactivity` is deliberately not wired in here.

The consequence that falls out of that split: **the inventory reports what it could not reach.**
If 500 ids come in and the user can see 340, that is the boundary working — but an artifact listing
340 rows silently reads as a complete footprint, and somebody handing over work would conclude the
other 160 do not exist. Unreachable ids appear with a reason, never dropped. Same asymmetry as the
labels code, for the same reason: the dangerous direction is reporting a partial sweep as a whole
one.

### Wave 4 — the Google-side controls · `0.42.0`

Issues: #336 (Sheets protected ranges), #337 (`copyRequiresWriterPermission`, `writersCanShare`),
#338 (no drives API at all — shared-drive restrictions unreachable, `driveId` unreported).

The honest follow-through on the CINO's own point (2026-09-01): *if you actually want to prevent
destruction of data, you use Drive's controls and the sheet-level controls, which exist.* Right now
this tool cannot set any of them. Capability gating is a ceiling below Drive's ACLs — these are the
layer that actually prevents the edit.

This is the first wave that adds capability rather than hardening, and the largest.

### Wave 5 — adoption · `0.43.0`

Issues: #339 (`copy_file` should carry the comments across — Drive v3 drops every one), #340
(document why comments are harder than they look), #286 (one place to read the controls, and a
guided setup).

#340 is the trust problem, and it is not a docs nicety: people do not believe this works with
comments **because they built their own tool, used the API, did not understand anchor text versus
cell identity, and never thought to export as XLSX and read them a second time.** Writing that down
is what makes the difference credible.

### Developer Preview is OFF the near-term list · decided 2026-09-04

**Nothing gated behind Google's Developer Preview Program is worked on before 1.0.0** (CINO).
The reason is not effort, it is audience: **most users of this library will not be enrolled**, so
building against the preview would ship a capability most people cannot use — and worse, a tool
description promising something that refuses for reasons the operator cannot fix.

That covers accept/reject of suggestions, native per-editor comments, and Sheets
`insertComment.coordinate`. All three are recorded as **UPSTREAM, gated rather than impossible**
in the refusal messages (`exceptions.UnsupportedOperation`), which is the honest state and needs
no further work to stay true.

Revisit when either the feature reaches GA, or a consumer says they are enrolled and blocked.

### Native editor comment APIs — post-1.0, behind a flag · decided 2026-09-02

Google's Docs, Sheets and Slides APIs each gained a **native** comment surface in Developer
Preview during mid-2026. Measured against the live API on 2026-09-02: all three exist, each anchors
in its own model (a character `range` in Docs, a `coordinate` in Sheets, an `objectId` in Slides),
and **all of it is gated** on enrolment in the Developer Preview Program. Background, measurements
and the corrections it forces: [`research/comments-apis-2026-09.md`](research/comments-apis-2026-09.md).

**Decision (CINO, 2026-09-02): stay on the Drive API. It works.**

- **post-1.0, possibly post-2.0.** No rush.
- Add it **before general availability**, so GA is not a scramble.
- **Behind a flag.** Most people are not enrolled in the preview, and a default most callers cannot
  use is not a default.
- **Coexistence, not migration.** Google has not announced deprecation of the Drive comments API,
  and it is the only option for non-editor files.

Two things worth knowing before anyone starts:

**It supersedes two "impossible" facts.** `insertComment.coordinate` is true cell-anchored comment
creation, and `sheets.commentAnchors` returns the comment→cell mapping *as a field* — which is the
entire job of `_cellmap.py` (XLSX export, `defusedxml` parse, three-hop relationship walk).
`acceptSuggestion`/`rejectSuggestion` also now exist. **Do not build a `PlaywrightBackend`**: those
two capabilities were its only stated justifications.

**The open question is identity, not capability.** Google publishes no interoperability guarantee
between the two surfaces, so *do native and Drive comments share an id space?* If not, reading both
and deduplicating falls back to content + author + timestamp heuristics — the kind of guess this
project refuses elsewhere. Unanswerable without enrolment, and it decides the shape of the work.

The `Backend` protocol is already the seam this slots into.

### A comprehensive comments reference — the resource that does not exist

**Goal: 20–50 pages, written primarily for an AI to read while implementing**, and readable by a
human who needs to understand what they are dealing with. Lives in this repository.

The premise is that **this programming resource does not exist anywhere**. Comments in Google
Workspace are genuinely hard, the knowledge is scattered across release notes, half-true
documentation, folklore in other people's source, and behaviour you can only discover by probing —
and the cost of not having it is visible: people build comment tooling, use the obvious API, get
anchoring wrong, and conclude it cannot be done. #340 is that problem stated from the user's side.

What it has to cover, at minimum:

- **The three annotation types and why they are not interchangeable** — comment (authored,
  threaded, repliable, resolvable), **note** (Sheets; no author, no thread, cannot be replied to or
  resolved), **suggestion** (Docs; accept/reject). A reply-and-resolve workflow has no destination
  for a note, which is worth stating before somebody discovers it.
- **The web editor's model**, because it is what users actually see and what every expectation is
  set by: what anchoring does when you select nothing, when you select across paragraphs, when you
  comment on an image or a table cell.
- **The Drive API v3 comments surface** — what it gives, what it does not, and the **four** anchor
  states with how to tell them apart (the fourth, a quote with no anchor, is API-only and was
  missed by an editor-only probe — #372).
- **That `quoted_text` is a claim and not evidence.** `quotedFileContent` is writable, Docs renders
  it verbatim as the document's own words, and validates it against nothing — so a
  commenter-level actor can quote text the document never contained, and can redirect a comment's
  apparent subject. Measured 2026-09-03, #380. Any document telling people how comments work has
  to say this, because every naive implementation trusts that field.
- **That an anchor can be REUSED but not MINTED.** A real `kix.*` id borrowed from an existing
  comment is honoured and renders as properly anchored; a synthetic one is not (#379). Google's
  "developer-defined anchors are treated as un-anchored" is about synthetic anchors only, and the
  distinction is invisible in the docs.
- **The native editor APIs** — per-editor anchoring, `PostAuthor.user` as a stable identity, and
  the preview gate.
- **The XLSX-export detour in full** — export, unzip, parse `threadedComments`, walk
  `workbook.xml` → `_rels` → per-sheet rels to recover *which tab*. Why `r:id` is not sequential
  (a real export numbers the first sheet `rId5`), why targets are relative, why a sheet with no
  comments has no relationship at all. This is the single most expensive thing this project
  learned and it is written nowhere else.
- **The measured quirks** — `resolved` absent on a never-resolved comment; soft delete stripping
  *both* content and author; resolve/reopen as an action-reply rather than a PATCH;
  `author.email` usually absent; `mentionedEmailAddresses` present but only if you ask for it.
- **Every "you would guess this and be wrong"** — API-written anchors stored verbatim and then
  ignored; `kix.*` opaque in Docs; `workbook-range` opaque in Sheets; Google's own published anchor
  example matching nothing the editors produce.
- **Decision guidance**: given what you are trying to do, which surface and which detour.

Source material already in the tree: `research/google-drive-comments-reference.md`,
`research/comments-apis-2026-09.md`, `research/docs-suggestions-reference.md`,
`experiments/anchor-probe/`, `experiments/docs-anchor-states/`,
`experiments/api-created-comment-states/`, `experiments/sheets-cellmap/`,
`experiments/comment-lifecycle/`, and `_cellmap.py`'s own docstring. The work is largely
**consolidation plus the gaps that consolidating exposes** — and every claim in it should carry
whether it was documented, measured, or inferred, because that distinction is exactly what is
missing from everything else written on the subject.

### The measurement gaps — what we do not know about comments, ranked

From [`research/comments-knowledge-map.md`](research/comments-knowledge-map.md) (2026-09-03), which
is the coverage map: every claim marked MEASURED / DOCUMENTED / INFERRED / UNKNOWN / UNTESTABLE.
These are its UNKNOWNs, in the order worth closing them. **Read the map before picking one up** —
it says what is already established, and roughly two thirds of the surface is.

**1. Assigned comments are invisible (#398).** `mentionedEmailAddresses` and
`assigneeEmailAddress` are real fields — a mask accepts them, an invented name is refused — and
**`fields=*` omits them**, which is its own gotcha. Our mask omits them too, zero occurrences in
`src/`. So *"which comments are assigned to me"*, the question a reviewer actually asks, cannot be
answered, and an action item reads as an ordinary comment. **The only gap here that is functional
rather than documentary**, which is why it is first. Decide the `__repr__` redaction at the same
time (invariant 2): these are real people's email addresses.

**2. Notification behaviour is completely unknown (#399).** Does a Drive-API comment email
anybody? **Both answers are operationally serious.** If it notifies, an AI review pass could
notify a whole team without intending to. If it does not, humans may never learn the comments
exist — which compounds two measured findings: API-created comments render as *"Original content
deleted"* and are **filtered out of the editor's default view** (#379). Needs a second Google
account, which is the cheapest unlock in the whole list.

**3. Slides comments have never been probed at all (#400).** We support them through the uniform
Drive axis and have never looked at what an anchor on a shape, a slide or speaker notes actually
contains. Everything we say about Slides comments is inference from the Docs and Sheets
measurements — which is exactly the reasoning that produced the three-anchor-state table that
turned out to have four members.

**4. The editor states nobody has placed.** Cross-paragraph selection, a comment in a table cell,
a resolved thread, an @mention, an assignment. Each needs a human in a browser — cheap, just not
scriptable, and the reason the zoo (#388) and the reference (#340) should be built together.

**5. Scale is unmeasured.** Everything here is measured on tens of comments; a consumer has run 90
threads. Pagination, rate limits, and what the XLSX-export detour costs at hundreds of comments
are all unknown.

**What is UNTESTABLE rather than untested**, and should not be planned around: every behavioural
question about the native comment APIs, including whether native and Drive comments share an
identity — the question that gates the dedup design. That needs Developer Preview enrolment. The
reference should ship that chapter **explicitly incomplete and marked UNTESTABLE** rather than
filled in from Google's documentation, which is the failure mode the map exists to prevent.

### A PUBLIC "zoo" of Drive files — the official reference corpus

**Goal: a public, link-shareable Google Drive folder holding one file per state this project has
measured**, kept indefinitely, cited by the comments reference above and by anyone reimplementing
this. Official CSA artifacts, not throwaways.

**Why it is worth real effort, and it is not convenience.** Almost every finding in this
repository came from a document somebody had to *build by hand*, because the interesting states
cannot be scripted: only the editor can mint a real anchor, only a human can select nothing and
comment, only a human can put a comment on an image. Every one of those documents has been
**trashed after use**. So each new question starts by rebuilding the fixtures, and each rebuild is
where the last round's careful setup is silently lost — `experiments/docs-anchor-states/` and
`experiments/api-created-comment-states/` both re-created the same numbered-paragraph document
from scratch.

**Three things it gives that the probe scripts cannot:**

1. **A citable artifact.** The comments reference is meant to be the resource that does not exist;
   a claim in it becomes checkable rather than assertable if the reader can open the file it was
   measured on. *"Comment B renders as `Original content deleted`"* is an anecdote until anyone
   can go and look.
2. **A regression canary against Google.** This is the strongest argument. Every behaviour here is
   Google's, undocumented, and can change without notice — and today nothing would tell us. A
   scheduled read of the zoo, asserting each file still exhibits its documented state, turns
   "Google changed the rendering of unanchored comments" from a thing a user reports into a thing
   CI reports. That is the same reasoning as `scripts/check_controls.py`: externally-enforced
   behaviour is asserted, not assumed.
3. **A fixture set for the native APIs, which is where it pays off.** The open question in
   `research/comments-apis-2026-09.md` §2.5 — *do native and Drive comments share an identity?* —
   is unanswerable without enrolment, and the moment we have it the answer requires exactly this:
   files with known comments, read through both surfaces and compared. Building the corpus now
   means the preview work starts at the measurement rather than at the setup.

**What must go in it** (one file per row, each self-describing in its own body):

| file | holds |
|---|---|
| Doc — anchor states | all four: file-level, object-anchored (image), text-anchored, quote-only |
| Doc — sloppy selections | nothing selected (caret snap), a three-word quote in a long paragraph, a selection crossing paragraphs, a one-word quote occurring four times |
| Doc — structure | headings at several levels, a table, an empty paragraph, a comment in a table cell |
| Doc — lifecycle | resolved, reopened, soft-deleted, a content-less action reply, a long thread |
| Doc — suggestions | accepted-view / rejected-view divergence, a replacement that is not collapsed |
| Doc — tabs | multiple tabs with comments on more than one |
| Sheet — cell mapping | comments across several tabs, including the `rId5`-numbering case, plus **notes** alongside comments |
| Sheet — headers | a table whose header row is *not* row 1, so `row_header`/`column_header` guess wrongly |
| Slides | a comment on a slide, on a shape, and on speaker notes |

**Constraints, and the first is absolute:**

- **Everything synthetic. No real content, ever.** This is public, permanently, and indexable.
  Same rule as the one forbidding extracted document data in the repo, with the stakes raised.
- **Comment authors are visible.** Every comment carries its author's display name, so whoever
  builds the zoo is publicly attached to it. Decide deliberately whether that is a person or a
  role account — a role account is the better answer and needs arranging first.
- **View-only sharing, plus a copy link.** If link-holders can comment, the corpus is polluted by
  the first curious reader. Share read-only and publish Drive's `?copy` URL so people experiment
  on their own duplicate. **Note that copying is itself a documented finding** — `copy_file` drops
  every comment (#339), so a copy is *not* an equivalent fixture, and the zoo should say so.
- **A manifest in the repo, with ids.** `experiments/zoo/MANIFEST.md`: file id, what it holds,
  which claim it evidences, who built it, when. Otherwise it becomes a folder nobody dares change.
- **An assertion script**, `experiments/zoo/verify.py`, read-only and runnable by anyone with the
  link — this is what makes it a canary rather than a museum. It needs no credentials beyond a
  read-only token.
- **Do not trash it.** Obvious, and worth writing down given that every predecessor was trashed on
  purpose.

**Effort:** the hand-built states are a couple of hours of careful clicking, and the manifest and
verifier are small. **Leverage:** high and compounding — it is the fixture set for #340, the
evidence base for every claim in it, the canary for Google changing behaviour underneath us, and
the setup for the native-API work whenever enrolment happens.

Sequencing: build it **with** #340 rather than before it. Writing the reference is what reveals
which states actually need evidence, and the zoo built speculatively would hold the wrong files.

### Versioning, regression recovery, and cleaning up somebody's mess — investigate before building

**The behaviour wanted, stated as a user would:** *"undo what Bob did in version X"* — recover from
a malicious edit, an accidental mess, or a formatting call that destroyed something, **without**
throwing away the good work that happened alongside it. Requested 2026-09-03 (CINO). #389 asks for
the read-only half; this is the whole problem.

**Probe first. It is not buildable in the obvious way, and that is measured, not assumed**
(2026-09-03, `experiments/revisions/`):

- **There is no revert method.** Drive `revisions` exposes `list`, `get`, `get_media`, `update`,
  `delete` and nothing else. A reset has to be read-then-write.
- **Read-then-write does work, with real fidelity.** Export the good revision as `.docx`, then
  `files.update` with it as media: bold runs recovered, `HEADING_1` preserved, the bad text gone,
  and it lands as a **new** revision so nothing is destroyed. Same upload-and-convert trick
  `_export.py` already uses.
- **`keepForever` is accepted and silently discarded on a Google Doc.**
  `revisions.update(keepForever=True)` returns **200**, reading the revision back shows the field
  absent, and the revision is pruned on the next edit anyway. Google's reference says the field
  applies only to files with binary content — so the semantics are documented and the API is wrong
  to accept the write. **This is the anchor trap again**: a write that reports success and does
  nothing. It means *you cannot pin the revision you might later want*.
- **Drive gives whole-document snapshots and nothing else** — no per-edit deltas, no change list.
- **And it keeps TWO of them. MEASURED**: 5 edits spaced **5 minutes** apart left exactly
  `['1', '7']` — the file's creation and the current head. Revisions 3, 4, 5 and 6 each appeared
  and then vanished. The five-minute gap was chosen to rule out coalescing-within-a-window, and it
  does. **So "read a past revision" means "read the state the file was created in"**, which is a
  very different capability from what the phrase suggests, and reset can only reach that state.
  `experiments/revisions/RESULTS.md`.

**Why "undo what Bob did" does not follow from revisions alone.** Attribution is *per revision*
(`lastModifyingUser`, singular) and revisions coalesce, so Bob's edits and Alice's can share one
revision with one name on it. The API cannot separate them, and diffing two snapshots recovers
*what changed*, never *who changed which part*.

**The missing half is the Drive Activity API v2** (`driveactivity.googleapis.com`), and it is
reachable: the client builds, `activity.query` exists, and it returns **403 insufficient scopes**
today because we do not request `drive.activity.readonly`. It gives per-file activity with
**actors** and action kinds — which is exactly the attribution revisions lack. It does **not** give
content deltas, so the shape is: **activity for who, snapshots for what.** Adding a scope is a
deliberate decision here (`SECURITY.md` names scope breadth as a risk), and it is the first
question to answer rather than a detail.

**The reframe that makes the whole thing exact, and its cost.** If *we* snapshot before editing,
the baseline is ours and both reset and selective reapply become diffs over artifacts we control
rather than guesses about Google's coalesced history. But that is a **new persistence surface**,
and this library states "no persistent storage of comment content" as a property — the same
tension #380 left open for a provenance log. **Decide that before building**, not after.

**Where the boundary has to fall.** Reapplying "the good edits but not the bad ones" is a merge
with conflict resolution, which is a *judgement* — and #358 settled that this library supplies
facts, not verdicts. The shape that respects both: we supply the base, the current state and the
attribution; a **model** proposes the merged document; we apply it and record all three. That fits
what this library is for, and it keeps the guess where a human can review it.

**Safety properties any implementation must have**, because this is the most destructive thing the
library would ever do:

- **never destroy** — always roll forward to a new revision, so the bad state stays recoverable;
- **an explicit revision id**, never "the last good one" inferred;
- **its own capability**, so it can be switched off independently of `content.write`;
- **say what will be lost before doing it** — the `.docx` round trip preserved bold and headings in
  the probe, but "preserved these three things once" is not "lossless", and the fidelity gaps need
  enumerating before anyone is told it restores a document.

Sequence: ~~measure revision durability~~ **(done: two revisions)** → decide the scope question →
decide the snapshot question → then design. The read-only half (#389) can still ship first and
independently, but it must **say** that the history is two entries deep rather than returning two
rows that look like a history.

**The durability result changes the conclusion rather than just informing it.** "Reset to a past
revision" was the tractable-looking half; with only the creation state reachable it is nearly
vacuous for a document anyone has been working in. So the snapshot decision is no longer an
optimisation for exactness — **it is the whole feature**, and there is no version of this that
rests on Drive's history.

### The conformance rig — a dedicated machine, agreed 2026-09-05

Spec: [`docs/superpowers/specs/2026-09-05-conformance-rig.md`](docs/superpowers/specs/2026-09-05-conformance-rig.md).

**Why it is now a priority rather than a nice-to-have:** every comment write was broken from
v0.47.0 to v0.51.0 — five releases, green CI throughout, because `FakeBackend` does not validate
field masks. `tests/integration/` would have caught it on its first test and had not been run in
five releases, because running it needs a browser login, a real Drive and a human to opt in.

Kurt is standing up a dedicated Mac. What it must do, in order: install **the latest PyPI
release** into a clean venv, **prove it is testing that wheel and not a checkout** (§3 — the
non-obvious part), run the live layers, and file **one deduplicated, redacted issue** per genuine
failure.

**Default posture is full read/write**, plus a separate layer (§5a) that proves the read-only
posture is refused **by Google** rather than by our own client guard. Nothing today tests that:
`tests/oauth/` covers read-only and its own docstring says it blocks writes *"at the client
guard"*, and #327 is the proof that this is not hypothetical — `has_write_scope` once accepted a
token carrying `drive.file` as read-only.

To build: `scripts/conformance.py`, the output redaction pass, the issue filer, **L2-RO**, the L7
editor layer, and `launchd` scheduling. The individual layers already run by hand today — §9 lists the
commands, and L3/L4 were verified on 2026-09-05.

### Parked

- **#297** prompt-injection research — got a real down payment in #312 (control-sequence
  neutralisation at the boundary). Revisit as research, not as a fix.
- **#113** the differential benchmark of ~18 AI security-audit tools into a CSA report. A
  publication project in a different mode from this backlog; do not let it queue behind polish.

### Decided, so it does not get re-litigated

- **#311 — reparenting is not a bug** (CINO, 2026-09-01). Inheriting the destination folder's
  permissions is what Drive does, and a human writer can already do it through the UI. Splitting
  parent mutation into its own capability would make this model **diverge** from Drive, which is the
  one thing the mirroring design exists to avoid. The defect is the sentence: spec line 107's *"our
  'move' is a rename"* is false and gets corrected, and `file.update`'s note should say reparenting
  changes inherited access. No gate change. Lands with wave 1 or 3, whichever moves first.
- **#330 — the 44-char Drive id in the fixtures is real** (CINO, 2026-09-01): an old Circle News
  file. Not a credential, not document content, and access is still governed entirely by Drive's
  ACLs. Closed, no action.
- **`clear_cells` stays `content.write`**, not `content.delete` — an agent that cannot blank a cell
  writes a junk value instead, which is worse for the sheet and harder to spot.

## Phase 2 — the built-in MCP server — ✅ SHIPPED (v0.2.0–v0.2.3, 2026-08-24/25)

`csa_google_workspace.mcp` is on PyPI: a local stdio server, **32 tools as of v0.22.0** on MCP revision `2026-07-28`
(SDK `mcp>=2.1`), with structured output on every tool and read-only/destructive
annotations, per-user OAuth via a separate `login` subcommand, and a CSA-branded consent page.
Spec: [`docs/superpowers/specs/2026-07-23-mcp-server-design.md`](docs/superpowers/specs/2026-07-23-mcp-server-design.md).

Built directly from the spec without a separate plan file — the spec's §10 phasing served as
the task list.

**Deferred from v1 — and all but two have since shipped.** Kept as a record of the ordering,
because the order was the point: nothing that could damage an existing file was exposed until
the control that scopes it existed.

- [x] **Content-write tools through MCP** — **done 2026-08-25** (v0.13.0), after allowlisting,
  exactly as this entry required. `replace_text`, `append_text`, `update_cells`, `append_rows`,
  `insert_slide_text`, all behind the single `content.write` capability.
- [x] **Docs suggestions** (`list_suggestions`) and the `as_text(suggestions=…)` preview —
  **done 2026-08-26** (v0.20.0). Read-only, because the Docs API has no accept or reject
  endpoint.
- [x] **Resources — the configuration ones, done 2026-08-25** (v0.11.0): `csa-gw://config`
  (effective policy, live) and `csa-gw://help/configuration` (the reference), plus a
  `describe_configuration` tool for clients that do not surface resources.
- [ ] **The document-text Resource and comment-triage Prompt** — both in the spec, neither
  built. **Not 1.0.0 gates:** both are conveniences over tools that already exist, and neither
  shapes a contract, so they can land any time.
- [x] **A launcher shim for Claude Desktop on macOS** — **done 2026-08-26** (v0.22.0), as
  `csa-google-workspace-mcp configure` rather than a shim. Gate D2; see there for why writing
  the config beats documenting the absolute path.
- [x] **Verify the PowerShell setup scripts** — **done 2026-08-26.** They had never been run,
  and the first real run crashed the terminal. Gate D1 has the root cause, which generalises to
  any PowerShell installer.
- [x] **File allowlisting — scope a `Workspace` to specific files and operations**
  ([#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82)) — **first
  control shipped 2026-08-25** (v0.7.0–v0.10.0): per-capability gating, two fail-closed URL
  lists, named profiles, enforcement in a `Backend` wrapper so library embedders and MCP clients
  get one guarantee. It **did** land before the mutating tools, which is what made
  write-on-by-default defensible rather than merely convenient. The open remainder — folders,
  per-capability scope, expiry, dead-entry detection, dry-run — is Gate A4.

## Where everything stands — the three buckets

**Sorted 2026-08-30.** Every open item has a bucket and a reason. Details are in the sections
below; this is the index.

### 1.0.0

| item | note |
|---|---|
| **#273 threat-model amendment** | Access-request text is a new untrusted-input class (outsider with NO access). Filed as an issue because the register may not be edited directly |
| **C6 MCP Registry listing** | **Pinned 2026-08-31** — waiting on the registry *inventory* in `ModelContextProtocol-Security/mcpserver-marketplace`, then submit to all of them at once |
| ~~Allowlist dry-run + dead-entry detection~~ | **Shipped** — one feature, `preview_allowlist`: a dead entry is what a dry-run finds |
| ~~`CONTROLS_TOKEN`~~ | **Done 2026-08-31** — PAT configured; all three controls now verify in CI. **Rotate by 2027-09-01**, see the banner at the top |
| ~~Drive labels~~ | **Shipped** v0.34.0 — read-only by construction; needs a 2nd API and a new scope |
| ~~`accessproposals`~~ | **Shipped** v0.33.0 — `resolve` gated as `file.share`, confirmed by Google's own scope table |
| ~~C2 flavour switch~~ | **Shipped** v0.32.0 — allowed *and* advertised; `claude` 14 tools, `google` 11 |
| ~~C4 logging~~ | **Shipped** v0.31.1 |
| ~~C3 caching knob~~ | **Dissolved** — never a gate, because a default-off cache is additive |

### Post-1.0.0

| item | note |
|---|---|
| **Provenance trust** | *Whose* files, not which. Gates on **potential**, because `displayName` is impersonatable so "who actually wrote" is unverifiable |
| **C5 uploaded formats** | **Blocked on** provenance trust — a dependency, not a queue position |
| **`.docx` comments** | Separate from C5's text extraction, and more interesting for a comments-first tool |
| **Traversal · corpus · revisions · vector search** | Contains the **probe** worth running early: does Google prune Docs revisions? |
| **THREAT_MODEL is stale on defaults** | RR-003 found the reversed-defaults claim in §3/§4 too *(34 tools, fails closed)*. **Not editable** — that is the audit's frozen text and the only baseline this repo cannot change. Either §0 supersedes it in prose (as T19 already does) or the follow-on security audit replaces the register. See *THREAT_MODEL needs updating* |
| **Can prompts resist injection?** | **Research, expecting "no"** (CINO 2026-09-01). We author ~49 KB of instructions + tool descriptions per session; more defensive wording costs context budget for an unmeasured benefit. Gated on *how would "improved" be measured* — an eval harness may be the real deliverable. Narrower than #297. See *Can the prompts themselves resist injection?* |
| **Scoping — research first** | **#82 closed 2026-09-01** having shipped its core. What is left needs research, not a design: scoping now has **two motivations that want opposite things** — containment (host-set, hard to change) and *context management* (user-set, easy to change). See *Scoping needs research before design* |
| **Per-capability scope · allowlist expiry** | Both weakened by the defaults reversal |
| **Document-text Resource · comment-triage Prompt** | Conveniences over tools that already exist |
| **Docs `batchUpdate` breadth · MCPB bundle · `PlaywrightBackend`** | Unchanged |
| **The API inventory** | **Committed wholesale** — all of it gets built, timing by value |

### 2.0.0 — a change in the *shape* of the tool surface

| item | note |
|---|---|
| **Multi-account** | An `account` parameter on every tool, or a server per account. PR #174 |
| **Hosted server · `files.watch`** | Different transport, auth model and threat model |

### Parked / closed

**#113** differential audit benchmark (parked) · **`Assisted-by:` trailers** (closed — nothing to
distinguish) · **the discovery question** (stale, shipped v0.15.0) · **`permissions.*`** (done
v0.30.14).

## No 1.0.0 milestone — keep shipping `0.N+1.0`

**Decided 2026-08-27 by the CINO: stop treating 1.0.0 as a thing to reach.** Ship
`0.N+1.0` improvements continuously and let the version number follow the work.

> **Amended 2026-08-30.** 1.0.0 came back, as a **bucketing device rather than a finish line**.
> Every open item now gets one of three answers — *1.0.0*, *post-1.0.0*, or *2.0.0* — and the
> question asked of each is "when", never "whether". That is compatible with the decision above
> rather than a reversal of it: the objection was to a milestone that shaped priorities, and a
> three-bucket sort does the opposite, because it forces the reasoning to be written down per
> item. Releases still ship continuously; the buckets say what a release is allowed to contain.
> **2.0.0 means a change in the SHAPE of the tool surface** — multi-account, the hosted server —
> rather than a size of change.

That matches how this project actually operates — **33 releases in five weeks** — and it
removes a milestone that was starting to shape priorities rather than reflect them. Items below
that were "gates" are now simply a **backlog ordered by leverage**. Nothing is blocked on
anything else, and none of them blocks a release.

### What this changes, and the one thing it does not

The gate list existed on a specific argument: *everything whose absence would force a breaking
change later*. Dropping the milestone weakens that pressure — but it does **not** remove it, and
the reason is worth being precise about, because it is easy to get the wrong relief here.

**The constraint was never the version number. It was whether anybody depends on the name yet.**
And they do: the server is installed through DesktopSetup, the research department was told about
it on 2026-08-27, and staff-wide is next. Every `CSA_GW_*` variable somebody puts in a client
config is a name we have to keep working, `API-STABILITY.md` or no `API-STABILITY.md`.

So:

- **Config-surface names still deserve care before shipping** — `CSA_GW_LOG_LEVEL`, the flavour
  switch's vocabulary, a caching knob's parameter, `account` and its enum. Not because 1.0.0 is
  coming, but because a config people wrote is a promise however the version reads.
- **Everything else is now ordered by value, not by contract risk.** Format breadth, the
  allowlist remainder, folders, expiry — take them when they are worth taking.
- **`API-STABILITY.md` needs no change.** It already says pre-1.0.0 nothing is frozen, and that
  stays literally true for longer than anyone expected. Its per-item table is the useful part
  and does not depend on a milestone.
- **The hosted server is still a separate thing** — different transport, auth model and threat
  model. That was never about version numbering.

The `C*` labels are kept below only because issues and commits reference them.

### Gate A — parity, because a reader will check — ✅ CLOSED 2026-08-25

The eight tools the other two servers had and we did not. **All eight ship**; every tool either
server offers is now here under the same name and argument shapes. Kept in full rather than
collapsed to a tick, because the order these landed in was the point: the destructive three
arrived *after* the gate that turns them off.

- [x] **A1** `search_files`, `list_recent_files` — **done 2026-08-25** (v0.5.0). The account
      axis exists: `workspace.files` is a `FileCollection` returning `FileRef`s, per the
      structure spec. Live-verified. It was the biggest usability win here — a session no
      longer has to begin with a pasted URL.
- [x] **A2** `get_file_permissions` — **done 2026-08-25** (v0.6.0). A `PermissionsMixin`
      beside `CommentsMixin`, since permissions are the same shape as comments: one Drive API,
      identical across all three types. Adds `public` / `writers` roll-ups so the model does
      not have to derive them. Live-verified.
- [x] **A3** `create_file`, `copy_file` — **done 2026-08-25** (v0.13.0). Gated on
      `file.create`, which is in the default `editor` profile: there is nothing existing to
      damage, and the *new* file is not in the modify allowlist either, so `create_file`
      followed by `append_text` is still refused unless an operator lists it. `create_file`
      takes Markdown in `content` and lets Drive convert it into real structure. `copy_file`
      checks the **read** scope, not modify, because it reads a source — and the copy it
      produces has a new id, so copying cannot manufacture a writable duplicate of something
      unwritable. → **completed Google's 8.**
- [~] **A4** **#82 allowlisting** — **dimension 1 done 2026-08-25** (v0.7.0), dimension 2 open.
      - [x] **Capability gating.** `policy.py`: named capabilities, a `Policy`, and a
            `PolicyBackend` wrapper that **fails closed** — a `Backend` method with no declared
            gate is refused, not delegated, so a new method arrives *off*. `CSA_GW_CAPABILITIES`
            is the complete permitted list, not a delta, so it reviews like code. Cannot be
            widened in-band. **Everything is enabled by default since v0.31.0** — narrowing is
            what an operator configures — and the four that cannot be undone are
            `comment.edit`, `comment.delete`, `content.delete` and `file.share`; recoverability
            now *orders the ladder* rather than deciding the default (v0.21.0 regrouping, A5).
            *(This said "Default refuses the three that cannot be undone". Two errors: the
            default refuses nothing, and `content.delete` made it four in v0.36.0.)*
      - [x] **Per-URL scope** — **done 2026-08-25** (v0.8.0, split by access kind in v0.9.0).
            Two flat lists of document URLs held **in the environment** —
            `CSA_GW_ALLOWLIST_READ` and `CSA_GW_ALLOWLIST_MODIFY`, no file — matched by
            file id. **Unset permits every file** since v0.31.0. What fails closed is a list
            somebody *tried* to write: a malformed entry, or one with no usable entries, is
            refused and the server does not start. Folder URLs are a **loud error**, not an
            inert entry. `search_files` results are filtered to the read scope — an excluded
            file must not even be *named*, or search becomes a way to enumerate what the policy
            hides. Denials log at WARNING.
            *(This said "Both fail closed: unset permits nothing, and `*` must be typed", which
            was true until the v0.31.0 reversal and is the same stale claim SECURITY.md carried.)*
      - [ ] **Split 2026-08-30 (CINO)**, because the four remaining pieces aged differently
            once the defaults were reversed in v0.31.0. Any structured format still has to stay
            *environment-shaped* — the policy lives in the client config, not a file, deliberately.

            **1.0.0:**
            - **dry-run** — *"what would this run touch, before it touches anything"*. It has
              grown **more** valuable, not less: conceived as a safety check under fail-closed
              defaults, it is now the honest answer to *"what does this install actually
              reach?"*, which is a bigger question when the answer is "everything unless you
              narrowed it". It also composes with two things decided the same day — previewing a
              **flavour** ("which tools would this register?") and later a **corpus enumeration**
              ("which 47 files would this index?"). Same shape, three consumers.
            - **dead-entry detection** — an allowlisted file that has been trashed. Cheap, and a
              silently dead entry is a policy that says less than its author believes.

            **Post-1.0.0 — and see [*Scoping needs research before design*](#scoping-needs-research-before-design)
            below, which is now the gate on all three.** #82 was closed 2026-09-01 having
            delivered its core ask; what is left is not a backlog of features to build but a
            question nobody has answered.
            - **session-level scoping** — the second half of #82's original ask, and the only
              piece of it never built or written down anywhere until now. A library embedder
              narrows a `Workspace` for one run: `with ws.scope(files=[id], ops={"comment"}): …`.
              #82 states the two properties that make it a control rather than theatre, and they
              are the whole design: it must be **monotonically narrowing** (a scope can only ever
              be a subset of the policy it inherits; widening raises) and **set by the host, not
              the guest** (the harness constructs the narrowed `Workspace` *before* handing it to
              the agent). If the agent controls the `with` block, it controls the scope.
              **The MCP server already has this property by a different route** — its policy is
              read from the environment at startup and no tool can change it — so this is a
              *library embedder* feature, which is why it did not arrive with the server work.
              Bounds an agent that has been **misled**; it does not bound one running arbitrary
              code in the same process with the credentials.
            - **per-capability scope** — *"commentable but not editable"* for one file. Needs a
              structured value the flat list cannot express, and the Drive-role profiles now
              cover most of what people actually wanted from it.
            - **expiry** — weakest of the four. It was designed when an allowlist was *the*
              boundary; it is now an opt-in scope somebody deliberately chose, and time-bounding
              a choice is much less compelling than time-bounding a grant.
      - [x] **The no-allowlist default: decided, flipped, and flipped back.** v0.9.0 made unset
            fail closed in the MCP server with `*` as the typed escape hatch; **v0.31.0 reversed
            it** — unset now permits every file, and narrowing is what an operator configures.
            What still fails closed is a list somebody *tried* to write: malformed, or with no
            usable entries, refuses to start. The library always kept a permissive default,
            because `from_credentials` is called by a developer who has made a decision while
            the server is configuration handed to a model.
            *(This entry described only the v0.9.0 state — the third place the reversed default
            was still being asserted, after SECURITY.md and the A4 capability entry.)*
      - [x] **~~Superseded by the broader model, eventually.~~** ✅ **Resolved by the item two
            above**, and the recommendation it made ("flip it at 1.0.0") was overtaken by
            actually flipping it in v0.9.0. Struck rather than deleted because it named a
            variable that no longer exists — `CSA_GW_ALLOWLIST=any` — and anyone who read this
            file earlier may still be looking for it. The current spelling is
            `CSA_GW_ALLOWLIST_READ` / `CSA_GW_ALLOWLIST_MODIFY`, and the escape hatch is `*`.
      - [ ] **Folders** — see the next section. Deliberately not attempted yet.

### What shipped is a first control, not the design

Worth stating plainly so nobody reads more into it than is there. v0.8–0.9 give **per-capability
gating plus two flat lists of document URLs**. That is enough to be concrete — a volunteer's
install is physically unable to change a document nobody listed — and it is enough to demonstrate
that the project takes the read→act path seriously. It is **not** a general authorization model.

A broader long-term design is **not** being designed yet — see [*Scoping needs research before design*](#scoping-needs-research-before-design), which is the gate on it, and of which this structured model is one candidate shape rather than the answer. Two properties of what is here should
survive into it, because they are what make it worth relying on at all: enforcement lives in a
**`Backend` wrapper**, so library embedders and MCP clients get the same guarantee from one
auditable place; and the policy **cannot be widened in-band**, because no tool changes it. Any
richer model that gives those up is a step backwards regardless of what else it adds.


### Scoping needs research before design

**Decided 2026-09-01 (CINO), on closing [#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82).**
The umbrella delivered its core ask — `PolicyBackend`, per-capability gating, two file
allowlists, fail-closed at the `Backend` seam. What remains (folders, per-capability scope,
expiry, session scoping, the structured allow/deny model) is **too useful to drop and not
understood well enough to build**. So it becomes a research task, and the research has to finish
before anyone designs the shape.

#### The finding that makes this research rather than implementation

Scoping now has **two motivations, and they want opposite things.**

| | **Damage containment** (#82's original framing) | **Context management** (the CINO's, 2026-09-01) |
|---|---|---|
| The point | bound what a *misled* agent can break | keep the model's working set small enough to be useful |
| Who sets it | the **host**, before the agent runs | plausibly the **user, mid-task** — "just this project" |
| Changing it | must be **hard**, and never in-band | wants to be **easy**, or nobody uses it |
| Wrong is | a breach | an annoyance |
| Stale membership | a security hole | a mild inconvenience |

A control that an agent can widen is theatre; an ergonomic scope somebody has to restart the
server to change is one nobody sets. **Those cannot both be one mechanism without deciding which
property loses**, and the honest possibilities include *two* mechanisms that happen to share a
matcher. Nothing in the existing design anticipated the second motivation, so its conclusions
should not be assumed to carry.

The context-management case is also the one with **real pull**: a working group folder of forty
documents is a natural unit of work, and "point it at this project" is what people actually ask
for. That is a stronger driver than the security case ever produced on its own.

#### What must be answered before a design

1. **Is scoping even the right lever for context?** If the goal is a manageable working set, the
   alternative is better *retrieval* — search and ranking that surfaces the right five files out
   of four hundred. A scope is a blunt instrument that a user maintains; retrieval is one the
   tool maintains. This question has to be asked first, because the rest is wasted if the answer
   is "index better, don't scope".
2. **What shape is a scope?** Flat file ids (what exists), a folder, a Shared Drive, a Drive
   **label**, a saved search, an explicit project manifest, or "what I touched this fortnight".
   These have entirely different cost, freshness and failure characteristics, and the current
   design considered only the first two.
3. **What does each cost?** One number is measured: **folder membership is live, so a folder rule
   costs one `files.get` per level on *every* access and cannot be cached** — which is why the
   structured model was deferred. Nothing else has been measured. What does a 500-file project
   cost to resolve? Does a label-based scope collapse to one query?
4. **Where does it live?** Environment (today, and deliberately — the client config is the
   artifact an operator can see), a config file, a file *in Drive*, a project file in the repo.
   The environment answer was chosen for a security control; a per-project ergonomic scope may
   want a different home, and that reopens a settled decision rather than extending it.
5. **How stale may it be?** Folder membership changes underneath you. For containment that is a
   TOCTOU gap; for context it is barely a defect. The answer differs *per motivation*, which is
   the tension in question 1 wearing different clothes.
6. **What does it compose with?** Capabilities, `CSA_GW_FLAVOUR`, session scoping, and the
   **local corpus / index** idea recorded elsewhere in this file — which is the same question
   from the other end, and whose safety rule (*anything found in an index is re-fetched through
   the normal authorized path*) is a constraint on any answer here.
7. **What is the prior art?** Google's own server sidesteps all of this with `drive.file`, where
   the user picks files and **Google** enforces it upstream. IDE workspace roots, git
   sparse-checkout and monorepo project files solve a recognisably similar problem. Somebody has
   probably been here.

#### What not to assume

- **That the flat-list matcher generalises.** It is fine for ids and cannot express a folder, a
  label or a query without becoming a different thing.
- **That the environment is still the right home.** It was the right answer to *"where does a
  security policy live"*.
- **That deferring folders on cost settles it.** That measured one shape against one motivation.
- **That this is small.** #82 stayed open for eleven days *after* its core shipped, mostly
  because "what is left" was never stated plainly. This section is that statement.

**Ends with a written comparison, in `research/`, and a recommendation** — the same shape as
`research/server-landscape.md`. A conclusion of *"scope by folder, accept the cost"* and one of
*"do not scope; improve retrieval"* are both acceptable outcomes. Implementation is a separate
decision that this research informs rather than presupposes.



### THREAT_MODEL needs updating — the audit's frozen text now describes the old defaults

**Noted 2026-09-01 (CINO), from RR-003.** A correctness review found the reversed-defaults claim in
`THREAT_MODEL.md` as well, in three places:

| line | says |
|---|---|
| `THREAT_MODEL.md:112` | *(the bundled MCP server exposes "34 tools" and "it fails closed")* |
| `THREAT_MODEL.md:131` | *(Both file allowlists fail closed when unset)* |
| `THREAT_MODEL.md:197` | *(both allowlists fail closed; `*` must be typed literally)* |

**Deliberately not edited, and that is the whole reason this is a TODO rather than a commit.** That
text is §4 and §3 — the audit's own words, frozen. The register's rule is that *threat text stays
as the audit wrote it while `status` is current*, and the frozen snapshot in the audit directory is
the one baseline this repository cannot edit, which makes it the only real check on a claim of
progress. Rewriting §4 to look correct would destroy that. `tests/test_threat_model.py` enforces
the boundary.

So the fix is one of two things, and it is a judgement call rather than a mechanical edit:

1. **§0 supersedes it in prose** — the cheap option, and the pattern is already established:
   T19's row already says *(the §4 text and the recommendation table below still describe branch
   protection as unverifiable; they are the audit's frozen words, and this row is what supersedes
   them)*. The same treatment applied to the tool count and the fail-closed language would make
   §0 carry every difference, which is what it is for.
2. **The follow-on security audit replaces the register** against the post-RR-003 public contract.
   That audit is already the intended next step, and it would rewrite these lines properly rather
   than annotating them — at the cost of leaving stale sentences in public text until it runs.

**Option 1 does not block option 2**, so the likely answer is both: annotate now, replace at the
audit. What must *not* happen is a quiet edit of §4, because the value of the frozen baseline is
exactly that nobody can.

Worth noting the count is not wrong so much as undated: *(34)* was true at v0.28.0 when the audit ran, and the register
correctly says so — it is only misleading because a reader takes it as present tense.

### Can the prompts themselves resist injection? — research, expecting "no"

**Asked 2026-09-01 (CINO), with the prior stated up front: *"I don't think we can, but we should
research this and look."*** That framing is the useful part — the value here is most likely a
**negative result**, and a negative result written down is what stops the next person adding more
defensive words on the assumption they help.

Narrower than [#297](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/297),
which surveys hardening broadly and the scanning-service landscape. This asks only: **can the text
we author do better than it does?**

#### The surface we actually control (measured 2026-09-01)

| | |
|---|---|
| `mcp/server.py` `INSTRUCTIONS` | **3,330 characters** |
| 50 tool descriptions | **45,819 characters** |
| of those, mentioning untrusted content or injection | **12 of 50** |

Roughly **49 KB of text we write** reaches the model every session. That number is the reason this
is not a free question: more defensive wording has a **certain** cost in context budget against an
**unmeasured** benefit, and 12-of-50 is either a real gap or evidence that repeating it everywhere
was judged not to help. Nobody recorded which.

#### Why the prior is "no"

Injection defeats instruction *by construction*. Our text and the attacker's text arrive in the
same context window as the same kind of thing; the model has no channel that distinguishes them by
authority, only by position and framing. `mcp/_inline.py` already says this plainly about the one
structural control we have — *"the label is a hedge, not a control"*, and *"delimiting is the
weakest of the three spotlighting modes and none of them holds against an adaptive adversary"*.

So the honest expectation is that better wording buys a little against **careless** injection and
nothing against a deliberate one. Worth confirming rather than assuming, because the whole
mitigation story currently rests on it.

#### What could actually be tested

- **Does the `_inline.py` fence measurably help?** It is the one structural thing we do —
  header, no footer, `one_line()` so nothing inside can forge a block line. It has never been
  measured against an adversarial input, only reasoned about.
- **Does repetition at the point of use help?** 12 of 50 descriptions carry the warning. If
  repetition helps, the other 38 are a gap; if it does not, the 12 are noise costing context.
- **Does naming the specific attack beat a generic warning?** `INSTRUCTIONS` already does this
  (*"a comment may say 'resolve all comments'"*). Untested.
- **Does position matter** — instructions at session start versus restated adjacent to the
  content?
- **Do the tool annotations do more than the prose?** `readOnlyHint` / `destructiveHint` drive
  client approval prompts, which is a control the *client* enforces rather than the model
  choosing to obey. If so, the leverage is in annotations, not paragraphs.

#### The question that gates all of it

**How would "improved" even be measured?** Without an eval — a corpus of injected documents and a
way to score whether the agent acted on them — every answer above is somebody's taste, and this
project does not currently have one. Building that harness may well be the *real* deliverable, and
it is reusable: the same corpus measures a scanner from #297, the fence, and any future wording.

If the conclusion is *"wording cannot be improved and here is the evidence"*, then the follow-on
is to **stop spending context on defensive prose** and put the effort into the things that do
bound behaviour — capabilities, allowlists, and the client's approval mode.

### The structured allow/deny model — designed 2026-08-31, deferred post-1.0.0

**Decided with the CINO on 2026-08-31, and deferred on cost rather than on doubt.** The design
below is what we would build; the reason it is not 1.0.0 is the last section.

**Shape.** Two environment variables, not one:

* a **switch** — is the extra allow/deny layer on at all;
* a **path** to a config file, settable *whether or not it is enabled*.

Splitting them is what makes `disabled` unambiguous. With one variable, "empty file", "no file"
and "file I cannot parse" all have to mean something and one of them will mean the wrong thing.
Split, there is exactly one rule: **enabled + unreadable or unparseable = refuse everything,
loudly** — the same shape as today's "three outcomes, and the third is the point".

It also allows the reviewable workflow: ship a config, have somebody read it, turn it on
separately.

**Rules, most specific wins:** `default < drive < folder < file`, with **deepest folder wins**
for nesting, so `/Projects` deny plus `/Projects/CCM` allow behaves the way anyone would read it.
Two shapes cover almost all real use: *"block X, Y, Z"* over an open default, and *"for this
project, default deny, then allow these drives/folders/files"*.

**Roles, not booleans, and they are Drive's own words.** Each rule carries
`deny | reader | commenter | writer` rather than allow/deny. Barely more complex, much more
expressive, and it **subsumes the deferred per-capability-scope item**. Use `reader`/`commenter`/
`writer` and **not** viewer/editor: this project already decided that for profiles (Google's UI
labels are refused by naming the API word), and two vocabularies for one concept is how a config
becomes guesswork.

**A config file, and NOT because of size.** Measured 2026-08-31: an env var holds ~512KB on macOS
(`ARG_MAX` 1MB, shared with args), and a URL plus a name is ~130 bytes — **~500 entries inside a
conservative 64KB budget**. Size was never the constraint. The file is justified only by
structure, and it costs the thing `allowlist.py`'s docstring argues for: a path is an indirection
whose target changes without the config changing. The enable+path split partly answers that, since
the path itself stays visible in the client config.

#### Why it is post-1.0.0: the cost is per-access and cannot be cached

A Drive file has **exactly one parent** — verified in the discovery document, "specifying multiple
parents isn't supported" — so the hierarchy is a tree and walking to the root terminates. That is
the good news, and it is not enough.

**Folder membership is a live property.** A file can be moved, so a folder rule has to be
evaluated *at every access*, not once. There is no ancestors endpoint, so that is one
`files.get` per level: a document four folders deep costs **four extra API calls on every
operation**.

**And the result cannot be cached, by this project's own rule:** caching authorization is how a
revoked grant keeps working. So it is a permanent 2–5× latency tax on every call, to enforce a
control that **Drive's ACLs already back-stop** — if the config says a file is editable and Drive
says otherwise, Drive wins. That ratio is what makes it a nice-to-have.

#### Two properties it would change, worth stating before anyone builds it

* **Today's list is id-based, so a *copy* of an allowlisted document is not allowlisted.** A
  folder rule inverts that: a copy made *into* an allowed folder is allowed.
* **Folder membership is mutable by other people.** "Allow folder P" means anyone who can move a
  file into P has granted the agent access to it; under default-deny that is an escalation path.
  Shortcuts sharpen it — a shortcut inside P targets a file anywhere. Changing the default does
  not remove this, only its direction.

A third option was considered and not chosen: **resolve folders at load time** into concrete file
ids. It keeps the authoring convenience and the id-based property and has no per-call cost, at
the price of needing a restart to see new files. Worth revisiting first if this is picked up.

### Folders in the allowlist — the design questions, unanswered

A folder URL looks like the obvious convenience: allowlist
`https://drive.google.com/drive/folders/1HXZ…` and let everything inside be writable. The
obvious implementation is *ancestor traversal*: on each access, `files.get(fileId,
fields="parents")` and walk up until an allowlisted folder appears or the root is reached.

**That works, and it is not safe, and the unsafety is not fixable by writing it more
carefully.** Recording why, plus everything else it drags in, so none of it is rediscovered
mid-build.

**1. Anyone who can add to the folder can grant write access.** This is the killer, and it is
why #82 already settled on *folder-as-generator, not folder-as-rule*. A WG folder may have
dozens of contributors. Any of them dropping a file in — or moving one in — silently extends
the agent's write scope to it. Worse, it works in reverse: someone copies a sensitive document
into the folder for convenience and it becomes agent-writable. The allowlist stops describing a
decision anybody made.

**2. Shortcuts break the traversal outright.** `application/vnd.google-apps.shortcut` is a file
whose parent is the allowlisted folder and whose `shortcutDetails.targetId` is a document
somewhere else entirely. Traversing the *shortcut's* parents answers "allowed"; the thing that
gets written is the target. Any traversal must resolve shortcuts and check the **target's**
ancestry, and must decide what to do when the target is unreachable. This is classic alias
confusion, and it is easy to implement without noticing.

**3. Multiple parents.** Drive has mostly moved to single-parent, but the API still returns
`parents` as a *list*, and older files can have several. If a file sits in folder A (allowed)
and folder B (not), "any allowed ancestor wins" makes the most permissive path the rule.
"All ancestors must be allowed" is defensible but surprising, and unenumerable in practice.

**4. Cost, and the cache that must not exist.** Traversal is an extra `files.get` per level per
access — for a document four folders deep, five calls before the write. The obvious fix is a
cache; but this project deliberately runs uncached (live multi-reviewer sessions), and a *security*
cache going stale is strictly worse than a data cache going stale: it means a revoked grant
still works for the cache's lifetime. Any caching here needs an explicit revocation story.

**5. Copies and shares.** A copy of an allowlisted document has a **new file id**, so under the
current flat list it is *not* writable. That is the right default and it should survive any
folder design. Note the asymmetry: id-based entries are immune to renames and moves (an entry
keeps pointing at the same document), whereas folder rules make a *move* into a silent grant and
a move out into a silent revocation — with no diff anywhere to review.

**6. Shared drives.** A file's ancestry terminates at a shared drive, not at "My Drive", and
`driveId` is a separate field. Traversal has to stop somewhere sensible, and "allowlist a whole
shared drive" is a much bigger grant than it reads as.

**7. Where does a newly created file sit?** `create_file` produces an id nobody listed. Today
`file.create` is `file_scoped=False`, because a new file cannot damage an existing one. With
folders in play the question sharpens: is a file the agent created inside an allowlisted folder
then writable? Saying yes lets the agent widen its own scope, one file at a time — which is
exactly the in-band widening the whole design forbids.

**The likely resolution, consistent with what #82 already settled:** keep the **flat id list as
the only enforcement primitive**, forever. Add folders as a **generator** — a command that
enumerates a folder *once*, emits the URLs it found with a comment saying where they came from,
and expects a human to commit the result. Then the TOCTOU disappears (the list is what was
reviewed, not what the folder currently holds), review remains possible (a `git diff` shows
exactly which documents were added), and enforcement stays O(1) with no extra API calls. The
cost moves to a process problem — the list must be regenerated when the folder changes — which
is a much better problem than a silent grant.

None of that is built. The questions above are the work.
- [x] **A5** `update_file`, `trash_file`, `share_file` — **done 2026-08-25** (v0.15.0), behind
      A4 as planned. Each has its **own** capability (`file.update`, `file.trash`,
      `file.share`), and each also requires the file in the modify allowlist. `update_file` is
      metadata only; `trash_file` is recoverable and there is no permanent delete anywhere in
      this library; `share_file` is the one call that can move data out of the organisation,
      which is why Google's own server declines to offer it.

      *(**Corrected 2026-09-02, #309.** As written on 2026-08-25 this entry added *"none is in
      any profile but `full`, so a default install cannot reach any of them"*. True then;
      **false since v0.31.0**, which enabled every capability by default and set both
      allowlists to `*`. The record of what was built stands; the claim about the default
      posture does not, and it understated the reach — the dangerous direction. What did NOT
      change is the other half of the sentence: each still needs its capability **and** the file
      in the modify allowlist.)*

      All three go through the **account
      axis** rather than `open()`, so they work on folders too. → **completed Claude's 11.**

      Two policy questions this raised, **both answered in v0.21.0** by regrouping the profiles
      on a single criterion — *can this be undone?*:
      - ~~`editor` has `file.create` and not `file.trash`, so it cannot clear up after itself.~~
        **`file.trash` moved into `editor`.** Trash is a 30-day bin the owner can see and
        restore from, so withholding it was withholding a *reversible* capability in order to
        produce *irreversible* litter in somebody's Drive. Wrong trade.
      - ~~`comment.delete` sits in `editor`.~~ **Moved to `full`, along with `comment.edit`.**
        Both are genuinely unrecoverable — Google keeps no comment edit history, and the soft
        delete strips content *and* author — so they belong with `file.share` rather than beside
        creating a comment. The old grouping had the default permitting the two irreversible
        operations while forbidding the reversible one.

      The regrouping exposed a **latent bug** in the demonstration: only capabilities that were
      off by default declared `requires`, so a `reader` or `commenter` profile already walked
      into refusals `demonstration_plan` was supposed to predict — sixteen of them, one at a
      time. `requires` is now derived from `TOOL_CAPABILITIES`, so a gated step cannot be
      unannotated.

**Still deliberately excluded from "parity":** their `read_file_content` covers 13 mime types
including PDF, Office and PNG/JPEG; ours covers the three Google-native types. Closing that
means parsing untrusted binary formats in-process, which is new attack surface and new
dependencies on the read path SECURITY.md calls the primary risk. Document the difference
instead. (Drive's own PDF/image → Doc conversion is not an option: it *creates a file*, so it
is not a read.)

### Gate B — the differentiator has to be reachable — ✅ CLOSED 2026-08-26

- [x] **B1 Content writes through MCP** — **done 2026-08-25** (v0.13.0), after A4 as required.
      `replace_text`, `append_text`, `update_cells`, `append_rows` and `insert_slide_text`, all
      behind the single `content.write` capability. "The only one of the three that can edit an
      existing document" is now true of the server as well as the library.
- [x] **B2 Docs suggestions through MCP** — **done 2026-08-26** (v0.20.0). `list_suggestions`
      returns them as objects (id, `insertion`/`deletion`, text) and `read_file_content` gained
      `suggestions="accepted"|"rejected"|"inline"`, which is the one that gets used: *"what would
      this document say if the edits were taken"* is the review question, and Google renders that
      preview server-side rather than us applying edits in our head.

      **Read-only, and the wording is the control.** The Docs API has no accept or reject
      endpoint, so the risk is not an exception - it is a model answering "done" to *"accept
      these"* when nothing happened. So the refusal is stated in the tool description, again in a
      `can_accept_or_reject` field of the result, and again in the `detail` string; a test asserts
      all three, because there is no API call to get wrong and therefore nothing else to check.
      Two smaller decisions: `tab` and `suggestions` together are **refused** rather than
      resolved (one is Sheets-only, one Docs-only, so honouring either would answer a different
      question), and there is deliberately **no `author` field** - Google exposes none, and a
      permanently-null field invites attributing an edit to nobody.

**Gate B is closed.** The library and the MCP server now expose the same capabilities; there is
no longer anything this project can do that a client cannot reach.

### Gate C — the part that literally *is* 1.0

- [x] **C1 A written API-stability and deprecation policy** — **done 2026-08-26** (v0.21.0):
      [`API-STABILITY.md`](./API-STABILITY.md). The **MCP tool surface is the contract** and the
      Python API is best-effort-but-serious, for a stated reason rather than by preference: a
      Python embedder breaks loudly, in their own test suite, having pinned a version; an MCP
      tool is called by a model reading a schema from a prompt written weeks ago, where the
      failure surfaces as *"I couldn't do that"* and sometimes with the message suppressed
      outright. The surface with the weaker feedback loop gets the stronger promise.

      Two things it settles that were not obvious: **which capability gates which tool is part
      of the contract** (moving a tool between capabilities silently changes what an existing
      config permits, so it is breaking with no name changed), and **profile membership is
      explicitly NOT** (they are curated sets, recurated in v0.21.0; name capabilities
      explicitly if you need an exact one).

      It also came with the **pre-1.0.0 API review** the policy is only meaningful with — see
      the v0.21.0 CHANGELOG entry for the three findings, two of which were defects that would
      have been permanent after 1.0.0.
- [x] ~~**C2 The flavour switch**~~ — **shipped in v0.32.0 (2026-08-30)**, with the rewritten
      scope intact: a flavour **allows only those tools AND advertises only those tools**.
      `CSA_GW_FLAVOUR=google|claude|full`, default `full`; `claude` publishes 14 and `google` 11
      (the vendor surface plus the three in `ALWAYS`).

      The advertising half is what made it worth doing — a model shown 36 tools behaves
      differently from one shown 8, however identical the names are — so the filter runs at
      **registration**, last in `create_server`, and a hidden tool answers `Unknown tool` from
      dispatch rather than a policy refusal from the backend.

      The refusal-legibility tradeoff was handled the way the rationale below requires: the
      restriction announces itself in the server instructions and in `describe_configuration`,
      which names the flavour and **counts what is hidden**. `authenticate`,
      `describe_configuration` and `read_server_resource` survive every flavour, because a
      restricted server must still be switchable-on and able to explain itself.

      What is left of the item is the open question below — **what `full` should say about
      itself** — which is a wording decision, not a gate. See `tests/test_flavour_switch.py`.
- [x] ~~**C3 Decide the caching knob**~~ — **removed as a gate 2026-08-30.** Not deferred:
      it was never a gate, and the feature has no stated reason to exist.

      **Nobody ever wrote down why we would cache.** The original design spec lists
      `_cache.py  # optional per-file cache (off by default)` in its file layout — a placeholder
      module, never built, carried forward as a TODO because libraries usually have a cache.
      There is no benchmark, no latency requirement, and no complaint anywhere in this
      repository.

      **The gate reasoning does not survive checking.** It said *"adding one later changes
      observable behaviour"*. That is only true of a cache that ships **on by default**, and the
      multi-reviewer argument says it never would. A default-off cache added in some later
      version changes nothing for anyone who does not opt in, so it is purely **additive**. The
      name-it-before-1.0 rule applies to things that must exist and whose vocabulary people
      write into configs — the log level, the flavour switch — not to an optional feature that
      may never be built.

      **And the case for it is weaker than it looks** (CINO, 2026-08-30):

      - **Offline is void.** No network means no Google Docs at all; a cache does not make the
        tool work offline, it only makes it wrong faster.
      - **Correctness costs the saving.** A cache you must validate before trusting is another
        round trip, so you save payload bytes and not latency — and latency was never the
        measured problem.
      - **Staleness lands exactly where the tool is used.** Live multi-reviewer sessions are the
        use case; a self-invalidated cache is silently wrong the moment a human resolves a
        thread you did not.

      **Requeued as research, not as work:** *does caching help at all — and if so, where?*
      Measure first: which calls are actually slow, whether anyone hits a Drive quota, whether
      an agent loop repeats reads within one session. Build nothing until a number says so.

      One thing to carry into that research: **a cache already exists.**
      `Sheet._cell_map_cache` holds the XLSX-export-derived comment→cell map, because building
      it means exporting and parsing the whole workbook. It is invalidated on `create_comment`
      and `batch_update`. So "this project runs uncached" is already not quite true — and it is
      the shape any future caching should copy: an internal detail with an explicit invalidation
      story, not a configuration knob.

      And the constraint from the folder analysis, which any such work inherits: **a security
      cache going stale is strictly worse than a data cache going stale** — it means a revoked
      grant still works for the cache's lifetime. Whatever gets cached, it is never
      authorization.
- [ ] **C5 Reading the text of uploaded files** — `.docx`, `.xlsx`, `.pptx`, `.odt`, PDF.
      **DECIDED 2026-08-30 (CINO): explicitly NOT supported, and blocked on security work rather
      than merely scheduled after it.** It does not ship until provenance trust — and whatever
      else that pass brings — is built. This is a dependency, not a queue position.

      **The gate itself is discharged**, because what had to land before people depend on the
      surface was never the parsing. It was one contract question: **does `read_file_content`
      ever create a file?** The answer is **no**.

      That rules out Drive conversion (`files.copy` to a Google-native mime) permanently, and
      rules it out for good reasons beyond the contract: it needs `file.create` *and* cleanup, so
      a **read** would acquire two write capabilities; it consumes the user's storage quota; and
      it litters their Drive if the process dies between create and cleanup. Under
      `API-STABILITY.md` it would also be **breaking with no name changed** — `PROFILE=reader`
      would stop being able to read a `.docx`, and the tool's `readOnlyHint=True` annotation
      would become a lie.

      With that answered, **in-process extraction is purely additive** whenever it does ship:
      `read_file_content` starts succeeding where it used to refuse, needing no new capability,
      and nothing an existing configuration says changes meaning. So there is no contract reason
      to hurry it, and a good security reason to wait.

      **What already works today, so the gap is narrower than it reads:** `get_file_metadata` and
      `download_file_content` both work on any file. Only *text extraction* is Google-native, and
      `read_file_content` already refuses with a message naming two workarounds — converting the
      file in Drive by hand, or taking the bytes.

      **When it is picked up**, the shape from the earlier analysis still holds: Office formats
      are zip + XML with a precedent already in the tree (`_cellmap.py` parses XLSX behind
      `defusedxml` and three size caps), and **PDF is the genuinely risky one** — a complex binary
      with a long CVE history in every parser, where *anyone who can share a file chooses the
      bytes*. Provenance trust is what removes that supply, which is exactly why this waits for it.

      **`.docx` comments are a separate question**, and a more interesting one for a
      comments-first tool: a Word document that has been through review is the same artifact as a
      commented Google Doc in a different container, but its comments live in `word/comments.xml`
      rather than in the Drive API. Also additive; also not urgent.
      **Added as a 1.0.0 gate 2026-08-27**, at the CINO's direction, after a plain question
      exposed how the gap actually behaves: *"if I upload a docx and call `read_file_content`
      on it, what happens?"*

      As of v0.28.0 metadata and raw bytes work on any file; only **text extraction** is
      Google-native. That is the one place either of the other two servers does more, and the
      README now says so in its own section rather than in a footnote.

      **Why it is a 1.0.0 gate rather than a feature request:** what a tool refuses is part of
      its contract. If `read_file_content` starts accepting a PDF after 1.0.0 that is additive
      and fine — but *how* it does so is not. Whether text extraction happens in-process or by
      converting through Drive changes what capability it needs (`file.create` for the second),
      whether it creates a file as a side effect of a READ, and what `SECURITY.md` has to say.
      Those are contract decisions, so the shape has to land pre-1.0 even if the parsing does
      not.

      **The risk is not uniform, which is the whole reason this needs deciding rather than
      installing:**
      - **Office formats are zip + XML and already precedented here.** `_cellmap.py` parses
        XLSX today with `defusedxml` plus caps on member size, total uncompressed size and
        member count (`_MAX_MEMBER_UNCOMPRESSED`, `_MAX_TOTAL_UNCOMPRESSED`, `_MAX_MEMBERS`).
        `python-docx` / `openpyxl` / `python-pptx` reuse that pattern rather than needing a new
        one. Lowest risk, highest value — most CSA drafts that are not Google-native are Word.
      - **Drive conversion parses nothing here.** `files.copy` with a Google-native target mime
        makes a readable copy, and Drive's OCR covers PDF and images. The catch is that it
        *creates a file*, so a read acquires a write side effect and needs `file.create` — the
        objection recorded in the README's export-formats section, which is a design decision
        rather than an impossibility.
      - **In-process PDF parsing is the genuinely risky one.** A complex binary format with
        embedded streams and a long CVE history in every parser (`pypdf`, PyMuPDF,
        `pdfminer.six`). This is what `SECURITY.md`'s primary-risk framing is actually about,
        and it deserves arguing on its own rather than riding in with the Office formats.
      - **OCR for images is out of scope** for 1.0.0: a native Tesseract dependency and
        variable output.

      Likely shape: Office in-process behind the existing hardening, PDF and images via Drive
      conversion, in-process PDF argued separately.

- [x] **C4 Logging** — **done 2026-08-29** (v0.31.1),
      [#145](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/145). The gate
      was right and the scope was wrong: it was specced as a logging *subsystem* and shipped as
      `CSA_GW_LOG_LEVEL` plus one line per tool call.

      **The check that shrank it:** the MCP client already persists our stderr. Claude Code keeps
      per-connection **JSONL** with a `sessionId` under `~/Library/Caches/claude-cli-nodejs/`;
      Claude Desktop keeps `~/Library/Logs/Claude/mcp-server-<name>.log`. Two clients, not
      coordinating. Their copy is also better than one written here — the *parent* capturing the
      *child* survives the server crashing, which a self-written file does not. So the log
      directory, JSONL writer, session ids, retention and `0600` handling were dropped before
      being built. Written up for every Python MCP server we build in
      `CINO-Engineering/research/mcp-servers/LOGGING-BELONGS-TO-THE-CLIENT.md`.

      **The "error store" half is not built and is not a gate.** What made C4 a gate was the
      config surface — the level name, spelled the way it will stay — and that has landed. A
      store can be added later without breaking anything.

      What the gate correctly predicted: raising the level had to mean **more about the
      operation, never more about the content**, because the client's free persistence lands our
      stderr in a cache directory nobody watches. Enforced, and verified by falsification in both
      directions.

- [ ] ~~**C4 the original scoping**~~ — superseded by the entry above. The old text argued for a
      dedicated `csa_google_workspace.audit` logger name on the grounds that introducing one
      later means asking people to change filters they already wrote. Still true, and still not
      needed: nothing today emits an audit stream distinct from diagnostics, and naming a channel
      before it has content is how a name ends up meaning something other than it says.

      Every log call in this library is `log.warning` — ten of them, no other level, no
      configuration. Three things follow, and the third is what makes it a gate:
      - **Levels are a config surface.** `CSA_GW_LOG_LEVEL` and the named postures have to be
        spelled the way they will stay, exactly like C2's flavour switch.
      - **A dedicated `csa_google_workspace.audit` logger is a name embedders filter on.**
        Introducing it later means asking people to change filters they already wrote; it is
        cheap now and impossible to retrofit quietly.
      - **Structured fields are a contract.** `API-STABILITY.md` already says log text and
        levels are *not* stable but that field names would join the contract if introduced —
        so deciding them after 1.0.0 means either a major bump or a promise made retroactively.

      Plus the half that is not about stability at all: the SDK suppresses the message on any
      exception that is not `ToolError`, and three of the six known SDK traps fail silently. A
      server whose errors the protocol can eat needs its diagnostics somewhere the protocol
      cannot reach. The three-tier design (in-session ring buffer · opt-in JSONL · consent-gated
      GitHub issue) is in #145; the off-box tier already exists as `report_a_problem`.

      Scope for 1.0.0 is deliberately the **contract-shaped part**: the level and posture names,
      the audit logger, `NullHandler`, no-stdout-ever with a test, and any structured field names
      written into `API-STABILITY.md`. The error store and the audit loop can land in 1.x —
      they add behaviour without changing what is promised.

### Gate D2 — release history and provenance

Housekeeping that only gets harder with time, and that a public 1.0 at a security organisation
should not skip. Prompted by noticing the changelog claimed versions nobody could install.

- [x] **Reconcile the changelog against reality** — done 2026-08-25. `v0.3.0` and
      `v0.4.0`–`v0.10.1` were development versions: bumped in code as each change landed, never
      tagged, never published, all shipped together as `v0.11.0`. `CHANGELOG.md` now says so at
      the top instead of implying eleven installable releases.
- [x] **Reconcile tags against PyPI** — done 2026-08-25, and it corrected this entry, which
      claimed 0.1.0 and 0.1.1 were untagged. **They were tagged**; the real discrepancy was that
      v0.1.0's changelog heading did not use the versioned format, so it read as unpublished.
      Now enforced rather than remembered: `tests/test_release_history.py` (offline, in CI) plus
      `scripts/check_release_history.py` for the three-way reconcile against tags and PyPI. It
      found the discrepancy on its first run, which is the argument for having it. Development
      versions stay untagged — a tag should mean released.
- [x] **PEP 740 attestations** — done 2026-08-25. They *are* attached: every artifact carries a
      bundle naming publisher `GitHub` and repository
      `CloudSecurityAlliance/csa-google-workspace`. The command to check one yourself, without
      asking us, is in `PROVENANCE.md`.
- [x] **Authorship stated** — done 2026-08-25 in [`PROVENANCE.md`](PROVENANCE.md): all non-bot
      commits are authored by Kurt Seifried, a large share of the content was AI-drafted under
      his direction and review, and **review is single-person** — which is the part that carries
      the weight, so it is named rather than implied.
- [x] **Decision index** — done 2026-08-25: [`docs/DECISIONS.md`](docs/DECISIONS.md). What was
      settled when, what evidence settled it, and which earlier belief it replaced. Corrections
      are rows of their own rather than edits, because being able to see that we believed
      something wrong is more useful than a clean record.
- [x] **Full-history secret scan** — done 2026-08-25 across 177 commits. **trufflehog: 0
      verified, 0 unverified.** gitleaks: one hit, triaged as a false positive — the
      `generic-api-key` rule firing on the entropy of a sentence containing
      `CSA_GW_INTEGRATION=1` — now allowlisted in `.gitleaks.toml` *with the reasoning*, so a
      real finding is not lost in noise. Both commands are in `RELEASING.md`'s pre-tag checklist.
- [x] **Yank policy** — done 2026-08-25, in [`PROVENANCE.md`](PROVENANCE.md#yanking). The bar is
      "installing this by accident is harmful", not "this is old": a leaked credential, data
      loss or corruption, a write the configured policy should have refused (the policy failing
      *open*), or an artifact not matching its tag. Not for an outdated surface or embarrassment.
- [x] ~~**Consider `Assisted-by:` trailers going forward**~~ — **closed 2026-08-30 (CINO): not
      doing it.** The premise was that per-commit attribution would make AI involvement
      greppable. It would not, because **there is no variation to record**: *"100% of this was
      written by AI with the human sitting in Claude Code, directing."* A trailer exists to
      distinguish, and a marker on every single commit is noise.

      What it did surface was an understatement worth fixing: `PROVENANCE.md` said *"a large
      share of the content"* and *"frequently not his keystrokes"*, which is weaker than the
      truth. Corrected — a provenance document that hedges its own central fact is worth less
      than no document.
- [x] **Add `scripts/check_release_history.py` to CI** — **done 2026-08-27**, as a step in the
      `lint` job. It already treated an unreachable PyPI as *skip the comparison* rather than a
      failure, so no guard was needed. Earns its place: it caught v0.27.0, which the changelog
      claimed was released and which had never been published.
- [x] **Assert the externally-enforced controls** — **done 2026-08-28** (v0.30.9, #189).
      `scripts/check_controls.py` checks the Trusted Publisher's environment binding, the `pypi`
      environment's required reviewers, and branch protection on `main`; weekly, and in the
      release build so a removed reviewer stops the release it would otherwise let through
      unattended. Reports OK / VIOLATED / **UNVERIFIABLE** and never counts the third as the
      first.
- [ ] **Folder support in the allowlist** — **deferred 2026-08-29** at the CINO's direction
      (*"lets do folder support later"*). The seven design questions below are unchanged and
      unanswered; nothing about the v0.31.0 defaults reversal makes them easier, and one of them
      gets *harder*: with the modify allowlist defaulting to every file, a folder list is
      something an operator opts into rather than the thing standing between an agent and the
      Drive, which lowers the cost of not having it.

- [ ] **Multi-account** — **targeted at 2.0.0, 2026-08-29** at the CINO's direction. It changes
      the shape of the tool surface rather than adding to it (an `account` parameter on every
      tool, or a server per account), which is what a major version is for. The analysis is in
      PR #174, deliberately left open: its central correction — that against prompt injection
      designs A and B are *identical*, because the model is the attack surface and process
      isolation does not stop the model being persuaded — stands regardless of when it ships.

- [x] ~~**Cover branch protection in CI, via an optional read-only `CONTROLS_TOKEN`**~~ —
      **done 2026-08-31.** Deferred to 1.0.0 on 2026-08-28 at the CINO's direction, then taken
      up: the PAT is configured and the weekly workflow now verifies **all three** controls
      unattended. Its first run reported `All externally-enforced controls verified.`; before
      it, branch protection read `[????]` in CI.

      **Rotate on or before 2027-09-01** — see the banner at the top of this file for the exact
      expiry and the permissions to grant. Two things learned installing it, both worth having
      written down:

      - **The first token was over-permissioned and it did not look it.** It could create
        issues (a probe accidentally opened, then closed, #268). Fixed by narrowing to
        `Administration: Read-only`.
      - **`GET /repos/{owner}/{repo}`'s `permissions` object is not evidence of a token's
        grants.** It reports the *user's* role in the org and reads `admin: true` even for a
        correctly-scoped token. The reliable test is a write that must be refused.

      The reasoning that deferred it is kept below, because the trade it describes is still the
      one to re-make at rotation time rather than renew by reflex.

      Two of the three controls above verify with **no credential at all**. Branch protection
      needs admin rights, and a workflow's `GITHUB_TOKEN` cannot be granted them — there is no
      `administration` permission to put in a `permissions:` block, so this is not a matter of
      asking for more scope. Covering it in CI means a fine-grained PAT with
      `administration:read` stored as a repository secret.

      **Why deferring is reasonable rather than lazy:** the control is checked *today* whenever
      the check is run locally with `gh auth token`, which `RELEASING.md` puts in the pre-tag
      checklist — so the release path, the place it matters, is covered by a human-run check. The
      gap is only the unattended weekly run. Against that, adding a long-lived credential to a
      **public** repository is a real and permanent cost, and it is the kind of thing to decide
      deliberately at a 1.0 review rather than to acquire as a side effect of closing an issue.

      When it is taken up: fine-grained, single-repository, `administration:read` **only**, and
      the weekly workflow already reads `secrets.CONTROLS_TOKEN` if present — no code change,
      just the secret. Worth pairing with a decision on rotation, since an unrotated PAT is how
      this kind of thing ages badly.

      *(That last sentence proved to be the whole of the remaining work. The secret took one
      command; the rotation date is the part that needed somewhere to live, and is now the
      banner at the top of this file.)*

- [ ] **C6 List the server in the official MCP Registry** —
      [registry.modelcontextprotocol.io](https://registry.modelcontextprotocol.io/). Added as a
      1.0.0 item 2026-08-27, at the CINO's direction (*"registered publicly"*). Mechanics:
      the `mcp-publisher` CLI, a `server.json` manifest declaring namespace, description and
      repository, GitHub OAuth to prove ownership, and the package already on PyPI — which it
      is. GitHub's own registry (the one that feeds Copilot and VS Code one-click install) is
      **separate** and worth doing too.

      **Why it is a 1.0.0 item rather than marketing:** `server.json` is a *published
      manifest*, so the name, the namespace and the declared install method become things
      other people's tooling resolves. Getting the namespace wrong is the kind of mistake that
      is permanent in the same way a PyPI version is. It also forces a decision this repo has
      so far avoided: what the canonical install instruction *is*, given there are three
      (`pipx`, the `[mcp]` extra, and DesktopSetup).

      Blocked on nothing technical, and the capability gates it was waiting behind are now done
      (labels shipped in v0.34.0, and the install story settled in #265 — which mattered, because
      the manifest has to declare a canonical install and there were three candidates).

      **Pinned 2026-08-31 (CINO), on a dependency rather than a doubt.** The official registry is
      not the only one, and submitting to it first would mean doing this once per registry as each
      is remembered. The inventory lives in
      [`ModelContextProtocol-Security/mcpserver-marketplace`](https://github.com/ModelContextProtocol-Security/mcpserver-marketplace)
      — a CSA project that already catalogues MCP servers and marketplaces — which the CINO is
      extending to list the registries themselves. **Then submit to all of them in one pass.**

      That ordering is worth the wait for a reason specific to this item: a `server.json` is a
      *published manifest*, and the namespace, description and declared install method are what
      other people's tooling resolves. Writing it once, against a known-complete list of consumers,
      is how the same name lands everywhere. Writing it per-registry as each is discovered is how
      three registries end up with three slightly different descriptions and one wrong install
      line.

      **Still to decide when it is taken up:** the namespace (likely
      `io.github.CloudSecurityAlliance/csa-google-workspace`, since ownership is proven by GitHub
      OAuth), and whether GitHub's own registry goes in the same pass.

This overlaps **C1** (the API-stability and deprecation policy): both are about what the project
owes someone who depends on it. C1 says what will not change; this says what did.

### Gate D — the unglamorous ones that will bite a colleague

- [x] **D1 Run the PowerShell scripts on real Windows** — **done 2026-08-26.** They had never
      been executed, having been written on a machine with no `pwsh`, and the concern was exactly
      right: the first real run **crashed the terminal outright** at the pipx step.

      Three stacked faults, and the root one is worth knowing for any PowerShell installer.
      Under `$ErrorActionPreference='Stop'`, a native command that writes to **stderr** raises a
      terminating `NativeCommandError` *even when it succeeded* — and inside
      `& ([ScriptBlock]::Create(...))` invoked from a `Stop` parent, **all six** redirection
      forms (bare call, `| Out-Null`, assignment, `2>$null`, `*> $null`, `2>&1 | Out-String`)
      kill the script **and its caller**. Standalone the same error is only statement-terminating,
      which is why isolated tests show everything surviving and the deployed shape dies. Fixed
      with an `Invoke-CsaNative` wrapper that sets `Continue`, plus a static analyser asserting
      every native call is wrapped — an analyser that then had to be fixed itself, because a
      six-line lookahead exempted exactly the region the wrappers live in and it found none of
      three deliberate violations.

      Verified on the real machine under the exact failing condition (3 MCP + 11 `claude`
      processes holding the venv), with a debug-log mode added so a failure arrives as a report
      rather than a description. Also fixed en route: a `$ghGate` variable read but never
      assigned (every Windows run would have reported "no access"), a clone token leaking into
      the debug log, and redaction that missed the `"client_secret": "…"` JSON form — the exact
      shape the OAuth file is written in.
- [x] **D2 Claude Desktop on macOS** — **done 2026-08-26** (v0.22.0):
      `csa-google-workspace-mcp configure`.

      The failure was never a bug, which is why it stayed open: Desktop is a GUI app, so it
      inherits launchd's `PATH` (`/usr/bin:/bin:/usr/sbin:/sbin`) — no `~/.local/bin`, no
      Homebrew, and its `python3` is macOS's 3.9, below our floor. Claude Code works because it
      runs in your shell, which is exactly what makes it read as "Desktop is broken".

      The README had documented the fix (an absolute path) for months. **That was a workaround
      with a hand-edit in it** — the user had to know their own home directory, produce valid
      JSON, and not clobber the other servers in a shared file. The tool knows its own absolute
      path, so it writes it: merges rather than replaces, keeps a timestamped backup, refuses
      rather than overwriting a file that does not parse, and carries the `CSA_GW_*` variables
      across because Desktop has **no shell** to read them from. Only those variables — it is
      reading an ambient environment that also holds cloud keys, into a file people screenshot
      when asking for help — and never `CSA_GW_CLIENT_SECRETS`, which only `login` needs.

      Also added `mcp/__main__.py`, so `python -m csa_google_workspace.mcp` works as the
      always-correct fallback when no console script can be found.
- [x] **D3 `Location.tab`, or an explicit limitation** — **done 2026-08-26** (v0.22.0), taking
      the second option, which the gate's own wording preferred: *a silently-wrong cell is worse
      than an absent one*.

      The consequence was worse than "tab is unknown". `_cellmap.parse_xlsx_comments` walks every
      `xl/threadedComments/*.xml` member — one per sheet — and collects them **flat, with no
      record of which sheet each came from**. So on a three-tab workbook a comment at B11 on the
      third tab is indistinguishable from one at B11 on the first, and `comments_by_cell("B11")`
      returned both as though the question had one answer.

      Now `comments_by_cell` returns `tab_ambiguous`, the `tabs` list, and a `detail` that says
      what the ambiguity *is* rather than that the answer "may be inaccurate" — and reports it
      **only when there is more than one tab**, because on a single-tab workbook the answer is
      exact and warning anyway is the check-that-fires-on-correct-behaviour mistake. `Location`
      now documents `tab` as *always `None` today*, meaning "not resolved", never "no tab" —
      kept on the model so resolving it later is not a breaking change.

      Resolution itself (`xl/workbook.xml` + rels, correlating member → sheet name) remains
      unimplemented and is no longer a 1.0.0 gate: the uncertainty is now stated where somebody
      can act on it.

### Explicitly not 1.0

| Item | Why not |
|---|---|
| **Hosted server, `files.watch` push** | **2.x.** Different transport, auth model and threat model. |
| **13-mime-type reading** | Untrusted binary parsers on the primary-risk path. Document the gap. |
| **#7 approvals · revisions · changes** | Genuine differentiators, purely additive — 1.1, 1.2, 1.3. |
| **#8 Docs `batchUpdate` breadth** | A programme, not a release gate. Tables first, post-1.0. |
| **MCPB bundle for Desktop drag-and-drop** | Distribution polish; does not shape the API. |
| **`PlaywrightBackend`** | For the API-impossible ops. Its own major decision. |
| **Provenance trust — whose files, not which files** | **Post-1.0.0.** Only interact with files owned by, and writable only by, trusted emails/domains. A genuinely new axis Drive cannot express, and the strongest answer to "should we parse untrusted binary formats". Gates on **potential** rather than history, because `displayName` is impersonatable and `emailAddress` is not guaranteed — which means the permissions list alone answers it and revisions are not needed. See below. |
| **Traversal primitive · corpus · revisions** | **Post-1.0.0**, one connected thread — see *Traversal, corpus and revisions* below. Folder walking with shortcut resolution; a local corpus for cross-file comment queries Drive cannot do at all; revision caching, which is the one thing genuinely safe to cache because revisions are append-only. Contains one **probe** worth running early: whether Google prunes Docs revisions, which decides how urgent the rest is. |
| **A local corpus — search, bulk analysis, vector index** | **Post-1.0.0.** Kept on the roadmap deliberately, and the framing matters: this is **not read caching** — that was dropped as unmeasured. It is about **capabilities the API does not have**, such as semantic search across documents. Needs a design first, and one rule is already settled: the index is for **discovery, never for answers**. Detail below. |

### Decided 2026-08-27

**No 1.0.0 milestone.** See the top of this section. `0.N+1.0`, continuously, with
config-surface names still getting care because people already depend on them.

### Decided 2026-08-25

**1.0.0 is a public release.** Local stdio MCP server, the Google/Claude flavour switch, and
#82 allowlisting — all three are gates, not stretch goals. **C2 (the flavour switch) is therefore
mandatory for 1.0, not a "should".**

Consequence to plan around rather than discover: public + full `drive` scope means **Google app
verification and an annual CASA assessment**. That is weeks of calendar time and a recurring
cost, and it is on 1.0's critical path — so start it in parallel with Gate A rather than after
Gate D. It is the one item whose schedule is not ours.

**`share_file` and `trash_file` both ship.** Built now; **#82 must land before 1.0.0.**

That leaves a window where destructive and exfiltration tools exist without per-file scoping.
Close the cheap half of it immediately: #82's requirement surface already has **two independent
dimensions** — global capability gating and per-URL scope — so ship both tools **behind a global
capability flag, default off**. That is #82's first dimension, not extra work, and it means no
default install can share or trash anything before the allowlist arrives. Per-URL scoping
follows with the rest of #82.

## Roadmap — nine subsystems, in order

**Six of the nine are done** (1, 3, 4a, 4b, 5a, 5b), and #2 shipped its first control. What is
left is #7 (approvals, revisions, changes+watch), #8 (Docs `batchUpdate` breadth), #9 (hosted
server), and the open remainder of #2.

Everything below this line was one item called "feature parity" until a code review showed it
is nine independent pieces with real dependencies between them. Each is its own spec → plan →
implement cycle; **do not try to plan them together.** At the granularity this project uses
(every task a failing test, a run, an implementation, a run, a commit) a combined plan runs to
several hundred steps and nobody executes it.

| # | Subsystem | Touches | Blocked on | Notes |
|---|---|---|---|---|
| ~~**1**~~ | ~~**Tool alignment**~~ — their names, argument shapes, and Claude's model-facing guidance | MCP layer only | — | ✅ **done 2026-08-25** (v0.4.0). |
| **2** | **File allowlisting** ([#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82)) | `Backend` wrapper | — | 🟡 **first control shipped** 2026-08-25 (v0.7.0–v0.10.0): capability gating, two fail-closed URL lists, profiles. It **did** land before 4 and 5, as required. Open: folders, per-capability scope, expiry, dead-entry detection, dry-run. See A4. |
| ~~**3**~~ | ~~**Discovery**~~ — `search_files`, `list_recent_files` | library: new axis on `Workspace` | — *(**not** 2 — see below)* | ✅ **done 2026-08-25** (v0.5.0). Biggest usability win: a session no longer begins with a pasted URL. Reads, so the write-narrow allowlist does not gate them — but `search_files` results **are** filtered to the read scope. |
| ~~**4a**~~ | ~~**File creation**~~ — `create_file`, `copy_file` | library: new axis | 3 | ✅ **done 2026-08-25** (v0.13.0). Gated on `file.create` after all — cheap, and it makes "may this install create files?" answerable. `create_file(content=…)` takes Markdown and lets Drive convert, which closes the document-pipeline loop. |
| ~~**4b**~~ | ~~**File mutation**~~ — `update_file`, `trash_file` | library: new axis | **2** | ✅ **done 2026-08-25** (v0.15.0), after 2. Rename/move and trash an *existing* file, each behind its own capability, neither in any profile but `full`. |
| ~~**5a**~~ | ~~**Permissions read**~~ — `get_file_permissions` | library | — | ✅ **done 2026-08-25** (v0.6.0). A read, so not gated. Adds `public` / `writers` roll-ups. |
| ~~**5b**~~ | ~~**Sharing**~~ — `share_file` | library | **2** | ✅ **done 2026-08-25** (v0.15.0), after 2. Still an exfiltration primitive and still one Google's own server declines to ship — which is why it needs `file.share` named explicitly, defaults to notifying the recipient, and refuses ownership transfer. |
| ~~**6**~~ | ~~**Format breadth**~~ — Markdown, PDF, Office, ODF, EPUB (**not** images) | `export` plumbing + a format table | — | ✅ **done 2026-08-25** (v0.4.0), with `_formats.py` and `download_file_content`. |
| **7** | **Differentiators** — `approvals`, `revisions`, `changes`+`watch` | 3 new API surfaces | — | Own brainstorm each. `approvals` is the most on-mission thing found. |
| **8** | **Docs `batchUpdate` breadth** — 37 unused request types | library | — | A programme, not a plan. Tables first. |
| **9** | **Hosted server** — unlocks `files.watch` push, and removes install/OAuth-client/login for everyone | new transport + auth + custody | **2**, and a CASA decision | Largest item here, and almost all of it is security rather than features. Own section below. |

### Correction (2026-08-25): #2 gates less than the table used to say

The table read "#3 blocked on 2" and "#5 blocked on 2". That was written before #82's shape was
settled, and the settled shape makes it wrong. #82 is **write-narrow**: *read stays as broad as
the credentials allow, only mutation is gated*, because the goal is damage containment, not
confidentiality — the agent already sees whatever the user sees.

Sort the eight parity tools by *whether they can damage something that already exists* and the
dependency falls out:

| Tool | Kind | Gated by #82? |
|---|---|---|
| `search_files`, `list_recent_files` | read | **no** |
| `get_file_permissions` | read | **no** |
| `create_file` | creates a new file | **no** — nothing existing to damage |
| `copy_file` | reads one, creates a new one | **no** |
| `update_file` | mutates an existing file | **yes** |
| `trash_file` | destroys | **yes** |
| `share_file` | exposes | **yes** |

**Those last three are exactly the three Google's own server omits.** So the two parity targets
have very different costs:

- **Google's 8 → five more tools, no #82 dependency.** Startable immediately.
- **Claude's 11 → three more on top, every one gated on #82** — and every one a tool Google's
  team looked at and chose not to ship.

What #2 still gates, unchanged: **content writes through MCP** (the library has them; the server
does not), plus `update_file` / `trash_file` / `share_file`.

### Why #2 must still come before the mutating half — and it is not only the security argument

**Every one of `Backend`'s 22 methods takes `file_id` as its first parameter.** That uniformity
is precisely what makes #82's `AllowlistBackend` trivial: wrap the backend, `policy.check(file_id,
op)`, delegate. No changes to existing methods.

The new operations break that shape:

- `search_files(query)` — **no `file_id` at all**, and it discloses titles and content snippets,
  which is information leakage even with nothing opened
- `list_recent_files()` — no `file_id`
- `create_file(title, content, parent_id)` — no `file_id`; it *produces* one
- `copy_file(file_id, …)` — has one, but also produces a new one

So #82 is not a security chore that can be deferred; it is **a schema decision with a
deadline.** Design the policy while 22 methods are uniform and the exceptions are deliberate.
Add discovery and creation first and the policy has to be retrofitted around them.

### First step — **shipped 2026-08-25** (v0.4.0)

**#1 + #6 together.** Done. It: ships the naming alignment and the transferability that
makes the flavour switch possible, adds format breadth almost for free, and leaves `mcp/` split
into a `_tools/` package — a shape that can absorb the rest. `server.py` is 265 lines with 10
tools today; the next dozen tools need that split regardless.

- Plan: [`docs/superpowers/plans/2026-08-25-tool-alignment-and-format-breadth.md`](docs/superpowers/plans/2026-08-25-tool-alignment-and-format-breadth.md)
- Shape it lands in: [`docs/superpowers/specs/2026-08-25-library-structure-for-the-roadmap.md`](docs/superpowers/specs/2026-08-25-library-structure-for-the-roadmap.md)

Two corrections that came out of writing it, both from probing rather than reading:

- **#6 is not quite "no library change".** It needs a small one — a per-type export-format
  table, because the formats genuinely differ (a Doc exports Markdown; a deck exports
  PDF/PPTX/ODP/text and nothing else). One shared enum would hand two thirds of callers an
  unfixable 400. Library, not delivery layer: it is domain fact, and library users want the
  same guard.
- **"images" was wrong.** Only *drawings* export PNG/JPEG/SVG, and the library cannot open a
  drawing. See [`experiments/export-formats/RESULTS.md`](experiments/export-formats/RESULTS.md).

### Why #6 is worth more than "a few more mime types"

`text/markdown` export is Drive's own conversion, so headings, lists, tables and links survive —
unlike `as_text()`, which is text runs only. That turns a Google Doc into a usable **source**
for a Markdown toolchain rather than a dead end, and CSA already has the toolchain: the internal
**`document-pipeline`** plugin (v2.3.1) takes *Markdown → tagged PDF/UA-1* with a design-rule
preflight, composition review, citations and CSA brand styling. **A public version is planned**,
which is what makes this worth designing around rather than treating as one org's convenience.

Drive also *imports* `text/markdown` into a Doc, so the loop closes:

    Google Doc --export text/markdown--> document-pipeline --> branded, accessible PDF/UA-1
         ^                                                                 |
         +----- import text/markdown (#4 create_file) <--- revised source -+

Draft and review where the comments are, typeset where the brand rules are, put the result back
where it can be reviewed again. The export half is #6 and lands now; the import half is #4 —
`create_file` should accept `text/markdown` and let Drive convert, rather than uploading plain
text and losing the structure.

## Provenance trust — whose files, not which files — post-1.0.0

**Decided post-1.0.0 on 2026-08-30 (CINO)**, after the design was worked through far enough to
see its real size. It began as *"defang the PDF parser"* and turned into its own capability with
an identity problem underneath it.

**The idea.** Only interact with files that are **owned by me, or by a trusted list of
emails/domains**, and to which **only trusted parties could have written**. A genuinely new axis:
the allowlist says *which files*, this says *whose files*. Drive cannot express it at all.

**Why it is worth having.** It attacks the **supply of attacker-chosen bytes** rather than trying
to harden a parser. Anyone who knows your email can share a file into your Drive today; provenance
trust removes that as an input path. It is the strongest available answer to *"should we parse
untrusted binary formats"* — which is exactly why C5 must not lean on it while it is unbuilt.

### The chain that forced gating on *potential* rather than *actual*

Worth recording, because the conclusion reverses the instinct and the reversal is earned:

1. **You cannot trust `emailAddress` on a `User`.** Documented: *"This may not be present in
   certain contexts if the user has not made their email address visible to the requester."*
2. **`permissionId` bridges it** — *"the user's ID as visible in Permission resources"* — so an
   unresolvable email can sometimes be resolved through the file's own permissions list.
3. **But `displayName` is user-settable**, so *"Bob wrote this revision"* means only *"someone
   whose display name is Bob"*. **Who actually wrote is unverifiable.**
4. **Therefore the gate must be on potential**, not on history — and once it is, **revisions are
   not needed at all**. They answer "who did", which cannot be verified; the permissions list
   answers "who could have", which can. One call, no identity resolution, no dependency on the
   revision-pruning question, and `get_file_permissions` already exists.

### The rule, which needs no `User` object

| permission | meaning | verdict |
|---|---|---|
| `type: anyone` + write | **anyone on the internet** could have edited it | refuse |
| `type: domain` outside trusted | anyone at that domain could have | refuse |
| `type: group` + write | membership is **not visible** from the Drive API | unresolvable → refuse |
| `type: user` + write, untrusted email | a named outsider could have | refuse |
| email unresolvable | cannot confirm trust | refuse |

**Unresolvable fails closed, and that is the correct direction** — if we cannot establish who
somebody is, we cannot confirm they are trusted. There is a helpful asymmetry: inside a Workspace
domain members' emails are generally visible to each other, while the accounts most likely to hide
one are external — the ones to refuse anyway. The link-shared case (`anyone` + `writer`) is the
single clearest untrusted-provenance signal available, and it is free.

### What makes it a feature rather than a check

- **Permissions are NOT append-only.** Revisions never change, so caching them is safe.
  Permissions are added, changed and **removed**, so a permissions cache can outlive the grant
  that justified a "trusted" verdict — staleness in the dangerous direction. And **permissions
  inherit from folders**, so one folder change silently flips the trust status of everything
  beneath it. Short TTL or explicit invalidation; it cannot work like the revision cache.
- **The authoritative history is not reconstructable by us.** Drive's API has no permission
  history — snapshots are all we can build, and ours only start when we start watching. The real
  record is the **Workspace Admin audit log** (Reports API): different API, admin-scoped,
  server-side. Same conclusion as everywhere else: the durable version lives on the server.
- **It interacts badly with the corpus.** Content indexed under a trust decision keeps that
  content after the decision changes. Corpus entries need the verdict recorded and re-validated,
  or purged when it flips.
- **It should probably gate writes too.** *"Do not edit a document anyone on the internet can also
  edit"* is at least as sensible as not reading one, and it is where an injected instruction and
  an unbounded grant combine.

### Open before any code

- [ ] Is `permissions.list` reliably readable for every file we can read, and how does it behave
      on **shared drives**? That decides whether "unresolvable" is rare or routine — and routine
      would make the control unusable rather than strict.
- [ ] Config shape: one variable taking `me`, emails and `*@domain`, applying to owner and to
      writers. A `permissionId` escape hatch for identities that never resolve.
- [ ] Reads only, or reads and writes.

### The consequence for 1.0.0

**C5 cannot count on this.** The PDF decision has to stand on its own merits, without provenance
filtering to lean on — which strengthens the case for declining in-process PDF parsing at 1.0.0
and saying so in `csa-gw://help/capabilities`.

## Traversal, corpus and revisions — post-1.0.0

Decided as a direction 2026-08-30 (CINO). **None of this is 1.0.0 work.** It is recorded here
because the pieces are related, several are cheap, and one of them has a closing window.

The organising idea, which is the same one behind `comments_by_cell` and `export_comments`
already: **the API is not the ceiling.** A vendor's own MCP server is a faithful wrapper over
their API and cannot exceed it. Ours is code running next to the data, so the API is an *input*
rather than the surface. That is where capabilities Google structurally cannot ship come from.

### 1. A traversal primitive

One low-level capability, several consumers: walk a Drive tree up and down, resolve shortcuts,
enumerate everything under a folder.

- **Shortcuts must be followed** — `application/vnd.google-apps.shortcut` →
  `shortcutDetails.targetId`. They are Drive's symlinks, and ignoring them silently omits files.
- **Cycle detection is required, not optional.** A shortcut pointing at an ancestor is a loop,
  and the failure mode is a hang rather than an error. Depth limit as well.
- **The result must be materialized and reviewable** — a list somebody can look at ("these 47
  files"), not a generator resolving invisibly. That property is what makes folder scoping safe
  *here* when it was rejected for the allowlist; see below.

### 2. Folder-as-corpus-scope is a different question from folder-as-allowlist-scope

`#82` rejected folders in the **allowlist**, and that stands. But most of its seven objections
weaken or invert when a folder is a **read/index scope** instead of an authorization scope:

| #82 objection | as a corpus scope |
|---|---|
| Anyone who can add to the folder grants **write** access | It is a **read** scope: worst case is an unexpected file indexed, not an attacker with write |
| Cost, and "the cache that must not exist" | **Inverted** — the enumeration *is* the artifact, done once at index time and kept |
| Copies get new ids; where do new files sit | Irrelevant when indexing what is there |
| Shortcuts, multiple parents, shared drives | Still real, but now "missed a file", not "security hole" |

The structural difference: **an allowlist folder is resolved per-access and invisible; a corpus
folder is enumerated once and the result can be reviewed.** Keep the two questions separate — one
may open while the other stays shut.

### 3. The corpus, and what it unlocks

Export sheets to CSV per tab plus a `-comments.csv` carrying the comments per cell, across a whole
folder, and you can ask things Drive cannot answer at all:

- *"show me everything Bob has said"* across forty documents
- *"show me all the comments and threads about topic X"*
- holistic review of a working group's whole folder

**This is absent by construction in Drive, not merely missing.** `comments.list` is a sub-resource
of a file — `GET /files/{fileId}/comments`. There is no `/comments` collection, and `files.list`'s
`q` has no comment predicate. Cross-file comment search requires iterating files and joining
locally. Google could not ship it in their own server without building the same thing.

**The value ladder, and the value is front-loaded:**

1. **Corpus + exact filters** — author, date, resolved state, file. This is a `GROUP BY`. No
   embeddings, no chunking, no staleness strategy. Most of what a reviewer actually asks.
2. **+ full-text** — *"mentions the shared responsibility model"*.
3. **+ embeddings / vector index** — *"about topic X"* semantically.

Do not lead with step 3. Step 1 is small and pays immediately, and `export_comments` already
produces most of the artifact.

**Two things that will bite, both already documented here:**

- **Identity.** `author.email` is *usually absent even when requested* (invariant #2, probe-
  verified). So *"everything Bob said"* is really *"everything by this display name"*, which is
  not unique and can change. CSA has a shape for this — Customer360 is identity resolution — but
  it is a real problem sitting under the most compelling query.
- **Threads are the unit.** `comments.list` returns replies inline, and resolve/reopen live in the
  replies. Flatten to one row per comment and you lose the audit trail and have to reassemble
  threads on read.

**The rule that makes it safe, and it is a security rule:** the index is for **discovery, never
for answers**. It must never become a way to *read* a document, only to *find* one — otherwise it
is a read-authorization bypass that persists on disk after a grant is revoked or a scope narrows.
Anything found there is re-fetched, and the re-fetch is where the allowlist and Drive's ACLs apply.

### 4. Revisions — the one thing genuinely safe to cache

**Revisions are append-only.** A revision, once it exists, never changes; only new ones arrive. So
a revision cache has **no invalidation problem at all** — you ask "are there newer ones?" and
nothing else. That is exactly the property document caching lacks, and it makes revisions the one
part of this API that is safe to keep locally.

Selective by design: cache a file's revisions, a folder's, or a folder plus its subtree — the same
granularity the traversal primitive gives everything else.

**We expose neither `revisions` nor `keepForever` today.** Nothing in the code.

### 5. `keepForever`, and the correction that matters

The instinct — *"if the history is critical, pin it server-side rather than hoarding it locally"* —
is right in principle and **does not work for the files we care about**:

| | `keepForever` |
|---|---|
| **Binary files** (uploaded `.docx`, PDFs, images) | Yes. Capped at **200 revisions**, which count against storage |
| **Google-native Docs/Sheets/Slides** | **Not applicable** — documented as only for files with binary content |

Google Docs revisions also cannot be *deleted* through the API; Google manages their retention
itself. The UI equivalent of pinning is "Name this version", which the API does not appear to
expose.

**So the durable-server-side answer may not exist for Google Docs**, which inverts the conclusion:
for native documents a local corpus would not be the convenient option for revision history, it
would be the **only** one.

- [ ] **PROBE, and it is the hinge: does Google actually prune Docs revisions over time?** The
      documentation says *you* cannot delete them. It does not say Google does not. One afternoon
      against a real document with known old edits settles whether revision-caching is a
      nice-to-have or the entire point. Probe beats docs; this repository has a directory for it.

**Worth having regardless, and cheap:** expose `revisions.list` and `keepForever`, so an operator
can *see* what is pinned — and, with the traversal primitive, **bulk-mark a whole folder's binary
files as `keepForever`**. That is a genuine capability: painful per-file in the Drive UI, trivial
in a loop, and it is the *preventive* answer rather than the hoarding one.

### 6. What this is for, and the policy question it raises

The motivating use case is **crediting volunteers**. Two people write paragraphs that are later
removed: was one good work that got rewritten and the other work that was simply deleted? That
matters to an organisation that runs on volunteers, and Drive cannot answer it.

**What attribution is actually available:**

| source | attribution |
|---|---|
| **Comments** | `author.displayName` — email usually absent |
| **Suggestions** | **none at all** — probe-verified; *"do not model a `Suggestion.author`, it cannot be populated"* |
| **Revisions** | `lastModifyingUser` per revision |

So **revision-diffing is the only route to attributing document text**: diff consecutive revisions,
credit the diff to that revision's `lastModifyingUser`. It is revision-granular, not paragraph-
granular — Google batches edits, so one revision may hold a lot of one person's work. Good enough
for *"Bob contributed this section that later went"*; not for *"Bob wrote these three sentences."*
And in a review-heavy workflow much volunteer contribution arrives as **suggestions**, which are
anonymous to the API entirely.

**The policy question, to be answered deliberately rather than arrived at.** A corpus that retains
*deleted* text, attributes it to named volunteers, and supports *"was that good work?"* has a
person on the other end. It is legitimate — crediting fairly is a real good, and crediting badly is
its own harm — but it deserves a stated position on retention, who may query it, and whether
contributors are told. Especially since we would be preserving precisely what the platform
discarded. Cheap to write down now; awkward to retrofit.

## Hosted MCP server — wanted, and a large piece of work

Wanted for real, not hypothetically: a hosted server is what unlocks **push notifications**
(`files.watch`), reacting the instant a comment appears rather than sweeping on a timer — and it
removes the install, the per-user OAuth client, and the `login` step for everyone.

It is also the single largest piece of work on this roadmap, and almost all of it is security
rather than features. Recording that honestly now, so nobody later mistakes it for "the same
server, on a box".

### Why it is not just a transport change

The local server has exactly one user, whose credentials live on their own machine. A hosted one
holds **per-user Google refresh tokens for many people** — each of which is full read/write/delete
on that person's entire Drive. `SECURITY.md` calls a single such token the crown jewel; this is
the crown jewels, plural, in one place, reachable from the internet.

### Inbound auth — the part MCP actually specifies

This is where MCP's OAuth framework finally applies: HTTP transports authenticate the *client to
the server*, which the stdio server deliberately skips.

- [ ] OAuth 2.1 **resource server**: validate every bearer token, reject anything not issued for
  us (RFC 8707 audience binding). **Token passthrough is explicitly forbidden** by the spec.
- [ ] Protected Resource Metadata (RFC 9728) + authorization-server discovery, so clients can
  find the AS. `WWW-Authenticate` on 401 with a `scope` hint.
- [ ] Client registration: **Client ID Metadata Documents** preferred; DCR is deprecated as of
  revision `2026-07-28` and kept only for compatibility.
- [ ] PKCE `S256`, mandatory. Refuse to proceed if the AS does not advertise
  `code_challenge_methods_supported`.
- [ ] **RFC 9207 `iss` validation** — new in `2026-07-28`, and required before an authorization
  code is sent to any token endpoint.
- [ ] Insufficient-scope handling: `403` + `WWW-Authenticate` with the scopes needed, so clients
  can step up rather than fail.

### Outbound Google auth — the part nobody specifies

- [ ] **Two token systems, never conflated.** The MCP client's token authenticates them *to us*;
  a separate per-user Google token authorizes *us to Google*. Mixing them is the confused-deputy
  vulnerability the spec names.
- [ ] Per-user Google refresh tokens in a real secret store, encrypted at rest, **isolated per
  user**. `Workspace.from_credentials(creds)` is already the entry point for this; the token file
  is not.
- [ ] Key management and rotation; revocation on offboarding that actually takes effect.
- [ ] **Reject domain-wide delegation** as the shortcut. A DWD service account can impersonate
  anyone in the org — a single key with more authority than every user token combined.

### Multi-tenancy

- [ ] One `Workspace` per request/user, never shared — the rule `SECURITY.md` already states,
  now load-bearing rather than advisory. `googleapiclient` clients are not thread-safe.
- [ ] No cross-user bleed in any cache (the `Sheet` cell-map cache is per-instance today; keep it
  that way).
- [ ] Per-user rate limiting and quota attribution, not global.
- [ ] Audit log of every mutation, attributed to a user, so a hijacked action is detectable after
  the fact.

### The push webhook itself

- [ ] Verified domain + valid certificate — Drive will not deliver otherwise.
- [ ] Validate the channel token on every delivery; treat the endpoint as **unauthenticated and
  hostile** until it is.
- [ ] Channel lifecycle: expiry, renewal, and cleanup of channels for revoked users.
- [ ] A public endpoint is new attack surface on a service holding many people's Drive tokens.
  Rate-limit and monitor it accordingly.

### And the thing that gets worse, not better

- [ ] **File allowlisting ([#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82)) matters more here.**
  Prompt injection through document content is the named primary risk; a hosted server runs that
  read→act path for many users continuously and unattended. The mitigation that does not depend
  on a model behaving well is the only one that scales.
- [ ] Public + full `drive` scope means Google **app verification plus an annual CASA
  assessment**. Real recurring cost, and a decision to make before building rather than after.

### Prior art in-house

CSA has already worked most of this shape out once: `CINO-Customer-360`'s
`docs/IT-SETUP.md` is a runbook for exactly this deployment — a FastMCP server behind an
**Internal** Google OAuth consent screen, secrets in AWS Secrets Manager, a Cloudflare Tunnel
hostname for the public surface, and Cloudflare Access in front of it. Start there rather than
from scratch. Two caveats: the tunnel is **specified but not deployed** there (`cloudflared` was
removed in its V1 — "we run no inbound web surface"), and its OAuth is `openid email profile`
only, i.e. *identifying* the user to the service. That is the inbound half. Holding a full-Drive
token per user on their behalf is the half nobody at CSA has built yet.

## Flavour switch — restrict this server to Google's or Claude's surface

- [x] ~~**`CSA_GW_FLAVOUR=google | claude | full`** (default `full`)~~ — **shipped in v0.32.0
  (2026-08-30)**. Registers only the tools the chosen server exposes, under their names and
  argument shapes. `mcp/_flavours.py`, `tests/test_flavour_switch.py`.

  **One deliberate gap, recorded rather than claimed:** the surviving tools keep **our**
  descriptions, not the vendor's. Names and parameters match — that was the alignment work — but
  copying Claude's model-facing wording is a separate, per-tool exercise, and ours carry guidance
  of their own (the untrusted-content rule, the `export_comments` steer). Left open below.

  The scope was rewritten 2026-08-30 (CINO) and shipped as rewritten. A flavour is a
  **surface guarantee**, and it has two halves that only work together:

  1. **Only those tools are allowed.**
  2. **Only those tools are advertised** — the rest are not registered at all.

  **The second half is the one that makes it real, and it is what the original framing missed.**
  Today a narrowed install still registers all 36 tools and refuses at call time, so a model
  sees a surface that does not match what it can do. That is not a drop-in replacement: the
  model behaves differently because it has different options in front of it, however identical
  the names are. Advertising without allowing is a lie; allowing without advertising is what we
  have now.

  Two of the three original reasons no longer carry it, and saying so is the point of this
  rewrite:

  - ~~*It forces the alignment work anyway*~~ — **already delivered.** The overlapping tools
    already carry matching names and argument shapes, verified against live schemas and
    documented in the README. That was the real value and it is banked without the switch.
  - ~~*Drop-in substitution* as a compatibility argument~~ — **software-mindset thinking.** API
    compatibility matters when *code* is pinned to names. A model reads schemas fresh each
    session and adapts. What a model does *not* adapt to is being shown tools that are not
    there in the server it is standing in for.
  - **A predictable, smaller surface** — still true, and now the whole justification. `google`
    is 8 tools with no share, no trash, no rename/move; that is a materially safer surface,
    chosen by a vendor who could have exposed more.

  **The tradeoff, handled rather than ignored — this is what shipped.** Hiding a tool changes
  what a refusal looks like.
  Today an agent calling `share_file` gets *"the `file.share` capability is disabled for this
  server; an operator enables it in configuration"* — informative, and relayable to the user.
  An absent tool instead reads as *"this server cannot do that"*, and the model may tell the
  user it is impossible or go looking for another route — the same route-around-a-refusal
  failure `csa-gw://help/capabilities` exists to prevent. So a flavour must **say what it is
  hiding**: a line in the server instructions and in `describe_configuration` naming the
  flavour and the count, pointing at `csa-gw://config`. Both landed. Three tools survive every
  flavour for the same reason — `authenticate` (or the server is bricked, not restricted),
  `describe_configuration` (where it says what it is hiding) and `read_server_resource` (the
  route to `csa-gw://help/capabilities`).

- [ ] **Policy-driven registration** — the same not-registering behaviour driven by the
  **policy** rather than by a vendor name: if `CSA_GW_PROFILE=reader`, do not advertise the write
  tools. **Now cheap**, because v0.32.0 built the machinery — the filter in `create_server` takes
  a set of names; only the input differs. It needs no new vocabulary, works for *any* narrowing
  rather than two vendor shapes, and serves the context-hygiene argument directly.

  It also needs the same care about legibility, and a bit more of it: a `reader` install that
  simply lacks the write tools cannot tell a model *why*, and "an operator can enable it" is
  exactly the sentence a user needs. Reuse `_flavours.describe`'s shape — say what is hidden and
  how many.

- [ ] **Copy the vendor descriptions**, per tool, under `claude`/`google`. Verified detail: the
  names and parameters are identical between Google's and Claude's servers; only the
  *descriptions* differ, and **Claude's carry extra model-facing guidance** (e.g. "do not put
  document-type words inside `title`/`fullText` clauses") that exists because models get it
  wrong. Worth having; not a gate, because a description mismatch degrades quality rather than
  breaking substitution.

  Prerequisite: implement the overlapping tools with matching names and argument shapes
  (see the coverage section below). The verified detail that matters — the tool *names and
  parameters* are identical between Google's and Claude's; only the *descriptions* differ, with
  Claude's carrying extra model-facing guidance (e.g. "do not put document-type words inside
  `title`/`fullText` clauses"). Copy that guidance: it exists because models get it wrong.

- [ ] Decide what `full` says about itself. A flavour that is a superset of both should be
  explicit in its server description that it can edit documents and hold full-Drive scope, so
  nobody arrives from a read-mostly connector and assumes read-mostly behaviour.

## Underlying API capability inventory — what we could build

**Committed wholesale 2026-08-30 (CINO): "we'll just do all that, either pre 1.0.0 or post
1.0.0."** So this stopped being a menu and became a backlog — everything here gets built, and the
only open question per item is *when*, answered by value rather than by a bucket decision. Two
items were pulled out and dated explicitly (`accessproposals` and Drive labels, both 1.0.0);
everything else is taken when it is worth taking.

That is a deliberate change of status for this section, and it removes a recurring cost: each of
these was being re-litigated as "should we?" every time it came up, when the answer was always
going to be yes eventually. The list is long, individually small, and mostly additive — three
properties that make per-item scheduling more expensive than just doing them.

**Two things that stay true regardless of order.** Anything mutating needs a `_GATES` entry and a
capability decision, because `PolicyBackend` fails closed on an unlisted method — so "just add
it" is never quite just adding it. And anything reading needs to inherit the untrusted-content
posture rather than assuming a new endpoint returns something safer than the last one.

Enumerated from the discovery documents (see
[`research/drive-mcp-servers-and-api-surface.md`](research/drive-mcp-servers-and-api-surface.md)).
This was the honest ceiling of the Python client — but several items are closer to
"help people get work done" than more file management would be.

### Drive v3 — exposed by nobody, including us

- [ ] **`approvals`** — a **document review workflow already in the API**, adjacent to the
  comment workflow this project owns. The strongest item on this list. Ships as four tools:
  `list_approvals` (`approvals.list`/`get`), `start_approval` (`approvals.start`),
  `respond_to_approval` (`approve`/`decline`/`comment`), `reassign_approval`
  (`reassign`/`cancel`). Worth its own brainstorm: an approval is a *state machine*, unlike
  every tool shipped so far, and the library has no precedent for modelling one.
- [ ] **`revisions`** — `list`, `get`, `update` (`keepForever`), `delete`. **Version history:**
  read a prior version, diff two revisions, pin one. Obvious pairing with suggestions review.
- [ ] **`changes`** — `getStartPageToken`, `list`, `watch`. Incremental sync: the correct answer
  to "sweep my documents" instead of re-reading everything, and it directly addresses the
  autonomous-sweep cost `SECURITY.md` worries about.
- [ ] **`files.watch` / `changes.watch`** — push notification. **Planned, for the hosted
  server** (see its own section below), not for local stdio: Drive push requires a publicly
  reachable HTTPS endpoint on a *verified domain*, which a process behind NAT cannot be.
  `changes.list` polling covers the same ground locally until then. This is a genuine want —
  reacting the moment a comment lands is a different product from sweeping on a timer.
- [ ] **`files.modifyLabels` / `listLabels`** — Drive labels, i.e. classification and data
  governance. **1.0.0 (CINO, 2026-08-30): "Drive labels need to be supported."**

  The one item in this inventory that is **security-adjacent rather than convenience**: labels are
  how an organisation marks sensitivity, and they are what Drive DLP rules key on. For a tool
  published by CSA, being able to read a document's classification before acting on it — and to
  set one — is closer to the point of the product than most of the list below.

  Read and write are different asks: `listLabels` is a read, `modifyLabels` changes a
  classification and should have its own capability rather than riding on `content.write`.
  Mislabelling a document is not a content edit.
- [x] ~~`permissions.*` (full: list/create/get/update/delete)~~ — **done**, and the gating note
  was stale. `list` and `create` shipped in v0.15.0; `update` and `delete` shipped **2026-08-29**
  in v0.30.14 (#235), both under `file.share` because ungranting is the same authority as
  granting. It was never actually gated on #82.
- [x] ~~**`accessproposals`**~~ — **shipped v0.33.0 (2026-08-30)**, as scheduled.

  **Checked before scheduling, and it does not do what the name suggests to an English ear.**
  Three methods — `get`, `list`, `resolve` — and **no `create`**. It does *not* let you request
  access to a file you cannot reach; it lets a file **owner see and approve/deny requests other
  people made** through the Drive UI. The other side of that interaction.

  Which makes it a better fit here than "request access" would have been: *"three people have
  asked for access to your WG document, here they are"* is a **triage workflow**, sitting next to
  comment triage, which is what this server is for.

  **Two capabilities, not one, and the split matters:**
  - `list` / `get` are genuinely read-only. *"Who is waiting?"* has no write in it.
  - **`resolve` is `file.share` in disguise.** Approving a proposal *grants a permission* — same
    outbound authority, same irreversibility once a copy is taken. It must be gated as
    `file.share`, however administrative "resolve a request" sounds.

  **Both calls were confirmed against the discovery document before building, and it settled the
  split empirically**: `list`/`get` accept the `.readonly` scopes, `resolve` demands `drive` or
  `drive.file`. Google classifies resolving as a write. `deny` ended up under the same capability
  too — gating it is conservative, but `action` is a caller-supplied argument and a gate that
  varied on it would let the untrusted side pick its own answer.

  **The probe also found the sharpest untrusted input in this project**, which was not
  anticipated when this item was scheduled: `requestMessage` is free text from somebody with **no
  access to the file**, reaching a model deciding whether to grant them some. Written up in
  `research/drive-mcp-servers-and-api-surface.md` §accessproposals.
- [ ] ~~`drives.*` — shared drive administration.~~ Out of scope: it does not help anyone
  review a document.
- [ ] ~~`files.delete` / `emptyTrash` — **permanent** deletion.~~ Out of scope for now. Both
  other servers stop at trash. That is a considered line, and an agent holding full-Drive scope
  with attacker-influenceable input in front of it is the worst possible holder of an
  irreversible delete.
- [ ] ~~`files.generateCseToken`~~ — client-side encryption tokens; no reviewer workflow needs it.

### Docs v1 — we use 5 of 40 `batchUpdate` request types

`documents.get` / `create` / `batchUpdate` are the only three methods; everything lives in the
request types. We use `replaceAllText`, `insertText`, `deleteContentRange`, `addDocumentTab` and
`deleteTab` — the last two since v0.36.0. Unused, grouped:

- [ ] **Tables** — `insertTable`, `insertTableRow`/`Column`, `deleteTableRow`/`Column`,
  `mergeTableCells`, `unmergeTableCells`, `pinTableHeaderRows`, `updateTableCellStyle`,
  `updateTableRowStyle`, `updateTableColumnProperties`. The largest single gap.
- [ ] **Styling** — `updateTextStyle`, `updateParagraphStyle`, `updateDocumentStyle`,
  `updateNamedStyle`, `updateSectionStyle`. Needed for anything that formats rather than types.
- [ ] **Structure** — `createHeader`, `createFooter`, `createFootnote`, `insertPageBreak`,
  `insertSectionBreak`, `createParagraphBullets`, `deleteParagraphBullets`.
- [ ] **Images** — `insertInlineImage`, `replaceImage`, `deletePositionedObject`.
- [ ] **Named ranges** — `createNamedRange`, `deleteNamedRange`, `replaceNamedRangeContent`.
  A stable anchor for repeated edits, which is a better primitive than raw indices.
- [x] ~~**Tabs** — `addDocumentTab`, `deleteTab`~~ — **done 2026-08-31** (v0.36.0):
  `Doc.add_tab`/`delete_tab`/`document_tabs` and the Sheets pair, with six MCP tools. What
  remains here is **`updateDocumentTabProperties`** — renaming or reordering a tab, which nothing
  in this library can do on either axis (there is no `updateSheetProperties` call either, so a
  Sheets tab cannot be renamed or moved). Add/delete/list is a complete enough set that renaming
  is a convenience rather than a gap, but "rename this tab" is a request a user will make.
  *(The `Location.tab` work this entry called deferred shipped in v0.37.0, #290.)*
- [ ] **Rich inserts** — `insertPerson` (smart chips), `insertRichLink`, `insertDate`.

### Sheets v4 — we use 6 of 17 methods

- [ ] `values.batchGet` / `batchUpdate` / `batchClear` — one round trip instead of N.
- [ ] The `*ByDataFilter` variants — address ranges by developer metadata rather than A1.
- [ ] `developerMetadata.get` / `search` — durable per-range annotation that survives edits.
- [ ] `sheets.copyTo` — copy a tab between spreadsheets.
- [ ] `spreadsheets.create`.

### Slides v1 — we use 2 of 5 methods

- [ ] **`pages.getThumbnail`** — render a slide to an image. The cheapest route to letting a
  model actually *see* a deck.
- [ ] `pages.get`, `presentations.create`.

## Coverage vs the Drive MCP servers  *(was: "feature parity" — premise corrected)*

> **Read [`research/drive-mcp-servers-and-api-surface.md`](research/drive-mcp-servers-and-api-surface.md)
> before acting on this section.** Reading the actual tool schemas overturned the premise this
> item was written on. In brief: the connector's **`update_file` is metadata-only** (rename and
> move), and **neither server can edit an existing file's content at all**. So "parity" is the
> wrong goal — the overlap is small, the differentiator (content editing, comment lifecycle,
> cell mapping, suggestions) is already ours, and the real gaps are **discovery, file lifecycle,
> permissions and format breadth**. The research note also surfaces `approvals` and `revisions`,
> two Drive APIs neither server exposes, one of which is a document review workflow.

Match the built-in connector's tool surface so anyone moving between it and this server does
not have to relearn anything — same names, same argument shapes, comparable prompt
suggestions and description. **With one deliberate divergence: say plainly that this server
does full read/write and is correspondingly dangerous.** The connector is a read-mostly
convenience; this is a full-authority tool on the user's entire Drive.

Its surface is 11 tools. Names below are the connector's own, taken from its live schemas
rather than screenshots:

**Read-only (6)** — `search_files`, `list_recent_files`, `get_file_metadata`,
`get_file_permissions`, `read_file_content`, `download_file_content`

**Write/delete (5)** — `create_file`, `update_file`, `copy_file`, `share_file`, `trash_file`

### Google's own Drive MCP server is deliberately narrower — and that is the finding

[Google ships one too](https://developers.google.com/workspace/drive/api/reference/mcp)
(`drivemcp.googleapis.com`), and comparing the three is more instructive than either
target on its own:

| | Google's official | claude.ai connector | this server (proposed) |
|---|---|---|---|
| Transport | remote HTTP | remote | **local stdio** |
| OAuth scope | **`drive.file` / `drive.readonly`** | — | **full `drive`** |
| Tools | **8** | 11 | 11 + comments/content |
| `update_file`, `share_file`, `trash_file` | **absent** | present | proposed |

Two things stand out.

**Google omits exactly the three most dangerous tools.** They control the API and could
expose anything; they ship `copy_file` and `create_file` but no update, share or trash. That
is not an oversight, and it is worth treating as informed opinion about which operations are
safe to hand a model.

**Google never uses full-Drive scope.** `drive.file` is the *per-file* scope: an app sees
only files it created or the user explicitly picked. That is **allowlisting, enforced by
Google**, and it is why their server can be relaxed about the rest — it physically cannot
reach the document the user did not choose.

This project needs full `drive` for a real reason: it opens arbitrary files the user names by
URL, which `drive.file` cannot do
([`SECURITY.md`](SECURITY.md) §Scope breadth). That is a defensible trade, but it means **we
gave up the safety property Google gets for free, and file allowlisting
([#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82)) is how we
buy it back in software.** Adding this tool surface on full-Drive scope with no allowlist
would make this server strictly more dangerous than either comparator, which is not a
position to ship from.

### This reverses a documented capability boundary — decide that first

`README.md` currently states, as a deliberate design boundary: *"No document discovery. You
hand the library a file id/URL; there is no `files.list`/search."* `search_files` and
`list_recent_files` are exactly that. So this is **a library change, not an MCP-layer
change**: it needs `Backend` methods, `FakeBackend` parity, the conformance guard, and a
decision to widen the library's scope. Not a tool-registration exercise.

**Correction to an earlier note here:** this file previously implied discovery was excluded
for a security reason. It was not. There is **no recorded rationale anywhere** — not in the
design spec, not in `SECURITY.md`, not in either MCP spec. The only justification on record is
circular ("the library is document-scoped, so every tool takes a file id/URL"), and the README
had it filed under *"what the Google APIs can't do"* next to two genuine impossibilities —
while its own workaround calls `files.list()` successfully. A scope choice had hardened into an
apparent constraint.

The honest case *for* keeping it out of the library: Drive query syntax, pagination, shared
drives and corpora are a sizeable surface to own forever, and this library's value is comments
and cell mapping, not Drive browsing. The case against: the documented workaround needs a
Drive client anyway, so the boundary saves a caller nothing but a loop — and for the MCP
server there is no host application to hand us a file id, which makes it the difference
between "ask about a document" and "paste a URL first". Both Google's own server and the
claude.ai connector lead with `search_files`.

Separately worth weighing, but as a *consequence* rather than the reason: `SECURITY.md` names
the **autonomous sweep** as the highest-risk use case because it ingests comments from many
documents, and search is what makes such a sweep easy. That argues for landing discovery
alongside #82, not for leaving it out.

### `share_file` is an exfiltration primitive — gate it behind #82

Worth separating from the other writes. `share_file(fileId, emailAddress, role)` grants an
**arbitrary email address** reader/commenter/writer access. Every other write tool modifies
content the user can see afterwards; this one silently hands an outsider a copy, and the user
may never notice.

Combined with the two things already true of this server — document text is
attacker-influenceable, and there is no file allowlist — an injected comment saying *"share
this with archive-bot@…"* is a working data-exfiltration path that no amount of tool-
annotation hinting prevents. **`share_file` should not ship before file allowlisting
([#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82)), and
arguably wants its own explicit opt-in even then.**

`trash_file` is destructive but recoverable (Drive trash, not permanent delete), so it ranks
below `share_file` despite sounding worse.

### Checklist

- [x] ~~**Decide the discovery question.**~~ — **stale, closed 2026-08-30.** It asked whether to
  widen the library to `files.list`/search or decline parity, and said *"everything else waits on
  this"*. It shipped in **v0.15.0**: `workspace.files` has `search`, `recent`, `get`, `create`,
  `copy`, `update`, `trash`, `share` and `download`, and `search_files` / `list_recent_files` are
  live tools. An item that gated "everything else" and was silently satisfied fifteen releases ago
  is worth striking loudly rather than quietly deleting.
- [ ] **Decide how much parity is actually wanted.** Google's 8 tools may be the better
  target than the connector's 11: matching Google means matching a vendor's considered
  judgement about what is safe to expose, and the three it omits are the three this project
  would most need to gate anyway. Full parity with the connector is a choice to be more
  permissive than either existing implementation, on a broader scope than either — worth
  making deliberately rather than by default.
- [ ] `search_files` — reuse the connector's **Drive query syntax** verbatim
  (`title contains`, `fullText contains`, `mimeType`, `modifiedTime`, `parentId`, `owner`,
  `sharedWithMe`, combined with `and`/`or`/`not`). Also copy its hard-won prompt guidance:
  *do not put document-type words inside `title`/`fullText` clauses; map them to `mimeType`
  instead* — that instruction exists because models get it wrong.
- [ ] `list_recent_files` — `orderBy` of `recency` | `lastModified` | `lastModifiedByMe`,
  page size default 10, token pagination.
- [ ] `get_file_metadata`, `read_file_content`, `download_file_content` — largely wrappers
  over what the library already does (`open`, `as_text`, `export`).
- [ ] `get_file_permissions` — new surface (Drive permissions API). Read-only but sensitive:
  it reveals who a document is shared with.
- [ ] `create_file`, `update_file`, `copy_file`, `trash_file` — new surface (Drive files API).
  Note the library is deliberately document-scoped today; file *lifecycle* is a new axis.
- [ ] `share_file` — **blocked on #82.** See above.
- [ ] **Tool descriptions and the server description must state the danger explicitly.**
  Parity of names must not imply parity of risk. A user who has used the connector will
  assume read-mostly; the description has to correct that before their first write.
- [ ] Prompt suggestions, matching the connector's shape.
- [ ] Pagination convention (`pageToken` / `next_page_token`) — the library has no paginated
  accessor today; `ApiBackend.list_comments` paginates internally and returns everything.
  Decide whether tools expose page tokens or keep hiding them.

## Publish — ✅ DONE

- [x] **Release automation** — `.github/workflows/release.yml` (Trusted Publishing / OIDC);
  steps in `RELEASING.md`.
- [x] **Published to PyPI** — `0.1.0`, `0.1.1` (docs patch), and `0.1.2` (first release
  through the hardened pipeline — attestations + env gate) all cut via `gh release create`
  → CI-built, tagged, GitHub-Released, uploaded over OIDC. Page:
  <https://pypi.org/project/csa-google-workspace/>. Since then: `0.2.0`–`0.2.3` (the MCP
  server and its follow-ups). Current `__version__`: **0.2.3**.

## Release-process / supply-chain hardening — ✅ DONE

From a 2026-07-23 release-process review (re-verified). Fixed in PR #69 (code) + repo-admin
settings, worst-first:

- [x] **⚙️ `main` is protected.** Branch protection via API: required status checks (`lint`,
  `test (3.10–3.14)`, `security`), PRs required, direct + force pushes blocked, **enforced for
  admins**. `required_approving_review_count = 0` so the solo/AI PR flow still merges (checks
  gate, no human-approval bottleneck). *Residual (optional):* also require the CodeQL contexts,
  and/or raise the review count if a second reviewer is ever available.
- [x] **🔧 Actions pinned to commit SHAs** (PR #69) — `checkout` v4, `setup-python` v5,
  `gh-action-pypi-publish` v1.14.1, across `tests.yml` + `release.yml`; Dependabot keeps them current.
- [x] **🔧+⚙️ Environment gate on publish** — protected `pypi` GitHub Environment (required
  reviewer: repo owner) + `environment: pypi` on the publish job (PR #69). **Residual now closed
  (2026-08-25):** the PyPI Trusted Publisher is constrained to environment `pypi` (was `(Any)`).

  Worth recording *why* this mattered rather than just that it is done. While the publisher
  accepted any environment, the approval gate was enforced only by a line of YAML **in the repo
  being published** — anyone able to edit `.github/workflows/release.yml` could drop
  `environment: pypi` and PyPI would still accept the upload. The control guarding releases was
  itself guarded by the thing it protects. Constrained at the registry, removing that line now
  *breaks* publishing instead of bypassing review: a convention became an invariant. Same move as
  `auth.load_cached_credentials` simply not containing the interactive branch.

  PyPI had been emailing this recommendation after every publish since 0.1.2 (five times).
- [x] **🔧 PEP 740 attestations** — `attestations: true` on the pinned publisher (PR #69),
  **✅ verified** against PyPI's **Integrity API**: `0.1.0`, `0.1.1`, and `0.1.2` all return
  `200` on `/integrity/csa-google-workspace/<ver>/<file>/provenance` — every release is
  attested. *Correction:* the earlier "no provenance" reading was a **measurement error** —
  the legacy `/pypi/<pkg>/<ver>/json` `urls[].provenance` field is unreliable (reads `false`
  even when attestations exist); use the Integrity API. Attestations have shipped since
  `0.1.0` (Trusted Publishing default), so there was never a gap to fix — the explicit
  `attestations: true` just makes it intentional.
- [x] **🔧 Security gate at release time** — `pip-audit` + `bandit` run before publish in
  `release.yml` (PR #69).
- [x] **🔧 Dependency automation + pinned build** — `.github/dependabot.yml` (`pip` +
  `github-actions`); `build`/`twine` pinned in the release job (PR #69). *(Full CI lockfile
  still optional/deferred.)*
- [x] **🔧 Polish** — `SECURITY.md` disclosure text completed; sdist-contents guard added
  (PR #69). *Deferred (optional):* SBOM publication; a post-publish "install from PyPI + import"
  smoke step.

## Tier 0 — audit findings (correctness) — ✅ DONE

Confirmed by an external review (2026-07-21), re-verified against the code, and fixed:

- [x] **`Workspace.open()` leaks a raw `HttpError`.** ✅ Fixed in PR #26. `ApiBackend.get_file_metadata`
  (`backend.py:190`) is the *only* data method that calls `.execute()` without
  `_errors.call(...)`, so the first call a consumer makes raises a raw
  `googleapiclient.errors.HttpError` on a missing/forbidden/service-disabled file
  instead of the typed `NotFoundError`/`PermissionError`/`ServiceDisabledError` the spec
  promises. **Fix:** wrap in `_errors.call`, **and** add an `ApiBackend`-level test that
  feeds a stub service raising `HttpError` and asserts typed translation — no
  `FakeBackend` test can catch this class of bug, because the fake raises typed errors
  directly (the one blind spot of the fake/real seam).
- [x] **Cell-map degrade is spec-noncompliant (no recorded warning).** ✅ Fixed in PR #26
  (stdlib `logging` WARNING on degrade; genuine no-match stays quiet). The spec
  (`docs/superpowers/specs/2026-07-20-csa-google-workspace-design.md:334`) requires
  `_cellmap` to degrade to `location=None` **plus a recorded warning**. `sheet.py:63`
  does the `location=None` half but records nothing, so export-cap-exceeded,
  access-denied, malformed XLSX, and genuine no-match are indistinguishable to callers.
  Shares a root cause with the tracked "10 MB export cap silently degrades" item:
  **there is no logging/warnings story.** **Fix (shared, minimal):** adopt stdlib
  `logging` + `warnings.warn`; closes both. Resist anything heavier.

## Tier 1 — make the "embeddable, typed" promise real (small, high leverage)

Both items below were independently flagged by the same external review — good signal
they're the right release-readiness priorities.

- [x] **`py.typed` marker (PEP 561).** ✅ Shipped in PR #27 (marker + `package-data`;
  verified present in a built wheel + a packaging test guards it).
- [x] **Package metadata.** ✅ Done: `readme`, SPDX `license = "Apache-2.0"` +
  `license-files`, `authors`/`maintainers`, `keywords`, trove `classifiers`
  (incl. `Typing :: Typed`), `[project.urls]`, and a single-sourced dynamic version.
  Bumped to `0.1.0`; `build` + `twine check` green for sdist + wheel.
- [x] **CI that runs the test suite.** ✅ Added in PR #28 — GitHub Actions runs
  `pytest -q` across Python 3.10–3.13 on push + PR (offline; live suite stays gated).

## Tier 2 — formalize the guarantees — ✅ DONE

- [x] **ruff + mypy in dev deps and CI.** ✅ ruff (lint; E/F/W/I/B/UP, ignoring the
  deliberate `E702` semicolon style, no auto-formatter) + mypy (`check_untyped_defs`,
  google stack marked untyped) now run as a dedicated `lint` CI job. Fixed the findings
  (mostly test cleanups + typing the injected `_backend`/`_file_id` fields and the
  `CommentsMixin` attributes).
- [x] **Coverage reporting** (`pytest-cov`). ✅ Wired into the CI matrix with
  `fail_under = 85` (total ~87%; the shortfall is the integration-only ApiBackend +
  interactive OAuth paths).

## Tier 3 — real API-surface gaps — ✅ DONE

- [x] **Sheets `append_rows`** (`spreadsheets.values.append`, `INSERT_ROWS`). ✅ Added;
  non-idempotent so never auto-retried on 5xx.
- [x] **Slides write symmetry.** ✅ Added `Slides.insert_text(object_id, text, index=0)`
  (shape-addressed, symmetric to `Doc.insert_text`) + `Slide.shape_ids` to discover
  targetable shapes. Decision: a fuller shape model (bulk shape CRUD) stays out — raw
  `batch_update` remains the escape hatch; the asymmetry with Docs is inherent (Slides is
  shape-addressed, Docs is a linear index).
- [x] **`Sheet.as_text(tab=…)`** ✅ now renders **all** tabs by default (each with a
  `# <tab>` header when >1), fixing the silent first-tab-only data loss; `tab=` selects one.

### Tier 3 minor / polish — ✅ already resolved (verified in code)

- [x] `replace_text` returns `occurrencesChanged` + `match_case` kwarg (Doc + Slides) —
  fixed in an earlier batch; a no-match (`0`) is distinguishable from a match.
- [x] `Sheet.batch_update` invalidates the cell-map cache (`self._cell_map_cache = None`).
- [x] `Doc.suggestions` is typed `list[Suggestion]`.

## Tier 4 — prove the pitch (scope-adjacent)

- [ ] **`examples/` reference consumer** — ~~a small MCP server or~~ a comment-triage bot
  built on the library. **Mostly superseded by phase 2:** the earlier "stays out of the
  *core* per the design" framing was reversed when the built-in MCP server was approved, and
  that server is now the reference consumer + the proof of the "embed in MCP/plugins"
  positioning. What's left of this item is only a *non-MCP* example (e.g. a plain triage
  bot), if one is still wanted after phase 2 ships.
- [ ] **Async story — decide.** Sync-only forces `asyncio.to_thread` on async callers. Lean:
  *document the `to_thread` pattern* (cheap) rather than build an async facade (large, and
  `google-api-python-client` is sync). **Phase 2 forces the call** — the MCP server is the
  first in-tree async-adjacent consumer, so decide it while writing that plan.

## Integration / live testing

Three tiers:

- **unit** — `tests/`, offline (`FakeBackend`), 217 tests; gates every PR.
- **integration** — `tests/integration/`, real Google API, opt-in via `CSA_GW_INTEGRATION=1`
  (needs a cached token or a first-run browser login). Covers the full surface incl. Tier 3.
- **oauth** — `tests/oauth/`, the **interactive browser-login** suite (real `from_oauth`,
  token-file permissions, `read_only` contract). **Separate** because it needs a human at a
  browser and touches the very sensitive cached token; own gate `CSA_GW_OAUTH=1`.

```
CSA_GW_INTEGRATION=1 CSA_GW_CLIENT_SECRETS=path/to/client_secret.json pytest tests/integration/
CSA_GW_OAUTH=1       CSA_GW_CLIENT_SECRETS=path/to/client_secret.json pytest tests/oauth/
```

- [ ] **Optional: a manual `workflow_dispatch` CI job** running the live suite with a stored
  Google credentials secret. **Deferred to the security audit** — putting Google creds in CI
  is a threat-model decision, not a default.

## Deferred — bigger / genuinely out of reach today (already tracked)

These are recorded design decisions, **not bugs**:

- [x] ~~**`Location.tab` resolution**~~ — **done 2026-08-31** (#290). The three-hop walk
  (`workbook.xml` → workbook rels → each sheet's rels → its `threadedComments` part) landed,
  and every consumer reports it: an `export_comments` `tab` column, `comments_by_cell(tab=)`,
  `CommentOut.tab`. Two things the probe corrected before any code was written — **`r:id` does
  not track sheet position** (a real export numbers the first sheet `rId5`) and relationship
  targets are **relative** — and one claim in the issue that had to be withdrawn: sheet identity
  **cannot** break `match_locations` ties, because the lookup side is a Drive comment and carries
  no sheet at all. The warning had to get *narrower* rather than wider: the old caveat fired on
  every multi-tab workbook, which would now cry wolf on the files this fixed.
- [ ] ~~**Caching pass** (as a read-through cache)~~ — **dropped 2026-08-30.** Accessors
  re-fetch per call and that is how it works, not a gap. The claim this item made — *"the biggest
  runtime win for embedded review sessions"* — was never measured, and three things argue against
  it: **offline is void** (no network, no Google Docs, cache or not); **validating a cache costs
  another round trip**, so the saving is payload bytes rather than latency; and **staleness lands
  exactly where the tool is used**, since a self-invalidated cache is silently wrong the moment a
  human resolves a thread you did not.

  **But that killed the wrong thing along with the right one**, and the distinction is worth
  keeping — see below.

- [ ] **A local corpus — search, bulk analysis, and possibly a vector index** — **on the
  post-1.0.0 roadmap** (CINO, 2026-08-30; see *Explicitly not 1.0* above). *A different idea from
  the cache above, despite sharing the word — and the framing is the point: **less about read
  caching, more about adding capabilities like vector search**.*

  **A read-through cache answers "can I skip this fetch?" A corpus answers "what can I do that
  the API cannot?"** Drive's search is filename-and-full-text over Google's index; it will not do
  semantic search, cross-document analysis, "which of these forty documents contradict the CCM
  mapping", or anything a local embedding index makes cheap. Those are capabilities, not
  optimisations, and none of the three arguments above touches them:

  - **Offline is still void for reads**, but a corpus is *useful* offline in a way a cache is not
    — you can search and analyse what you already have.
  - **Validation cost does not apply**: you are not deciding whether to trust a cached value in
    place of a fetch.
  - **Staleness is expected and fine**, because a corpus is for **discovery, never for answers**.
    Every search engine works this way. You search to find candidates, then read them
    authoritatively through the normal path.

  **That last line is the design rule, and it is a security rule, not a style one.** The index
  must never be a way to *read* a document — only to *find* one. Otherwise it becomes a
  read-authorization bypass that persists: content indexed while you had access is still there
  after the grant is revoked or the allowlist narrows, which is the "stale security cache" problem
  in a worse form, because it survives on disk. Anything found in the index gets re-fetched, and
  the re-fetch is where the allowlist and Drive's own ACLs apply.

  **The sync mechanism already has an entry**: `changes` (`getStartPageToken` / `list` / `watch`)
  in the API inventory below, which is exactly how a corpus stays current without re-reading
  everything.

  **Not scheduled.** Wanted, plausible, and needs a design before any code: what is stored, where,
  under whose retention, how it is invalidated, and how it is scoped per account. The
  `export_comments` register is the existing precedent for derived local data, and the
  `CSA_GW_LOCAL_*` switches are the existing precedent for letting an operator refuse it.
- [x] **10 MB XLSX export cap** — large sheets degrade the cell-map. ✅ No longer *silent*
  as of PR #26: the shared logging story records a WARNING naming the cause. (Raising the
  cap itself is still out of reach — it's a Google export limit.)
- [ ] **Accept/reject suggestions & true cell-anchored comment creation** — API-impossible
  (proven by probe); reserved for a future `PlaywrightBackend`. `ApiBackend` raises
  `UnsupportedOperation`.

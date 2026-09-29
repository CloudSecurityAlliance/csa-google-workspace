"""A dated snapshot of one person's document footprint, for a work handoff.

Somebody is unavailable — on leave for a month, or handing their work over — and a question
arrives that cannot wait for them. This answers *"where is their work, and what is in it?"* as a
flat table somebody else can work through.

Spec: `docs/superpowers/specs/2026-09-02-work-handoff-inventory.md`. Read it before changing the
shape here; the four decisions below were made deliberately and each has a reason that is not
obvious from the code.

## This is a snapshot, not a cache

Accessors re-fetch per call and there is no caching layer (settled 2026-08-30). That decision was
reasoned from the LIVE multi-reviewer case, where staleness lands in exactly the sessions this tool
is for. A handoff inventory is the inverse: the person whose footprint is being reconstructed is
not editing, so a frozen view is the correct answer and should not drift while a colleague works
through it.

Two things keep it from becoming a cache by the back door, and both are load-bearing:

**It is a deliverable, not an index.** The output is rows, destined for a dated CSV or Sheet that a
person is handed. There is nothing internal to invalidate and no hidden state.

**It is never an access path.** Reading a file's CONTENT still goes through the normal authorized
call. An id appearing in an inventory grants nothing.

## Edited and commented are separate signals

Kept apart on purpose, because they answer different questions and have very different costs.

`edited_last_by_subject` comes from Drive's `lastModifyingUser`, which is the MOST RECENT editor
only. **If the subject edited a file and somebody else edited it afterwards, the subject is
invisible in this column.** It answers *"did they touch it last"*, never *"did they ever touch
it"*. That is a property of Drive, not of this code: the complete answer needs `revisions.list`
per file, which is opt-in because the cost is the caller's to accept.

`comments_by_subject` is exact, because `comments.list` returns every author on every thread. It is
also the only cross-file view of somebody's commentary that exists — Drive has no `/comments`
collection and no comment predicate in `files.list`, so this is absent by construction there.

## What could not be reached is REPORTED, never dropped

The sharpest requirement here, and it follows from the delineation: this library runs **as a
user**, while the list of files to sweep may come from an administrator using a different tool.

If 500 ids come in and the user can see 340, that is **not a failure** — it is the boundary working
as designed. But a table of 340 rows *lies by omission*: it reads as a complete footprint, and
somebody handing over work would conclude the other 160 files do not exist.

So every id that could not be reached appears in `unreachable` with a reason. This is the same
asymmetry `labels.py` applies — an unreachable label is reported as `None` with a reason rather
than omitted, *because reporting a classified document as unclassified is the dangerous direction*.
Here the dangerous direction is reporting a partial sweep as a whole one.

## Derived columns are empty and stay empty

`summary`, `keywords`, `tags` and `notes` are always blank. They are the point of the artifact
being a worksheet rather than a printout, and they are the CALLER's to fill — this library does not
summarise. It is embedded in tooling that already holds a model; the moment it calls one itself it
acquires an API key, a cost model and a second trust boundary, and stops being embeddable.

There is deliberately **no read-back path.** `_apply.py` gives the comment register one, and
generalising it here would be wrong: a comment register is a set of intended ACTIONS on one file,
while this is a DESCRIPTION of somebody's work. Nothing in it is an instruction, and treating
`notes` as one would turn an analyst's jottings into Drive writes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from . import _export

# What the sweep OBSERVED. Ordered, because this is written as a header row.
REPORTED = (
    "file_id", "name", "type", "url", "drive_id",
    "owner_names", "owner_emails",
    "created_time", "modified_time",
    "last_modified_by", "last_modified_by_email",
    # The two signals, kept apart. See the module docstring for why the first is weaker.
    "edited_last_by_subject", "comments_by_subject", "last_comment_by_subject",
    # How the subject was matched on THIS row, so a reader can see it rather than trust it.
    "matched_on",
)

# What a person or a model FILLS IN. Always empty on export.
DERIVED = ("summary", "keywords", "tags", "notes")

COLUMNS = REPORTED + DERIVED

# Why an id in, but no row out. Not free text: a reader filters on these.
NO_ACCESS = "no_access"
NOT_FOUND = "not_found"
TRASHED = "trashed"
FAILED = "failed"


@dataclass
class Inventory:
    """The snapshot. `rows` is what was reached; `unreachable` is what was not, and why."""
    columns: list[str]
    rows: list[dict[str, Any]]
    unreachable: list[dict[str, str]] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    generated_at: str = ""
    subject: str | None = None

    @property
    def reached(self) -> int:
        return len(self.rows)

    def __repr__(self) -> str:
        # Redacted like every model here: a file title can be as sensitive as its contents and
        # embedders log these objects. `comments.py` sets the precedent.
        return (f"Inventory(rows={len(self.rows)}, unreachable={len(self.unreachable)}, "
                f"generated_at={self.generated_at!r})")


def _actor_names(actors: Any) -> tuple[str, str]:
    """`(names, emails)` as semicolon-joined strings, or `("", "")`.

    `None` (not asked) and `()` (a shared-drive file, which genuinely has no owners) both
    render empty here, because a spreadsheet cell has no third state. The distinction survives
    where it matters — on `FileRef` and in the structured MCP output — and the caveat below
    tells the reader what an empty owner column means, which a blank cell cannot.
    """
    if not actors:
        return "", ""
    names = "; ".join(a.display_name or "" for a in actors)
    emails = "; ".join(a.email or "" for a in actors)
    return names, emails


def _matches(actor: Any, subject: str) -> str | None:
    """How `actor` matches `subject`, or `None`. Returns the BASIS, not a boolean.

    Email wins when present, and the basis is returned rather than discarded because the two
    are not equally trustworthy: an email match is an identity, a display-name match is a
    guess. `TODO.md` records this as the real problem sitting under the most compelling query,
    and a reader who cannot tell which one happened cannot judge the row.
    """
    if actor is None:
        return None
    wanted = subject.strip().casefold()
    if not wanted:
        return None
    email = (getattr(actor, "email", None) or "").strip().casefold()
    if email and email == wanted:
        return "email"
    name = (getattr(actor, "display_name", None) or "").strip().casefold()
    if name and name == wanted:
        return "display_name"
    return None


def _iso(value: Any) -> str:
    return _export._iso(value) or ""


def build(refs: list[Any], *, subject: str | None = None,
          comments_by_file: dict[str, list[Any]] | None = None,
          unreachable: list[dict[str, str]] | None = None,
          now: datetime | None = None) -> Inventory:
    """Shape reached files into rows. Pure: no I/O, no backend, nothing to mock.

    `refs` are `FileRef`s already fetched. `comments_by_file` is what the caller managed to
    read, keyed by file id — absent means comments were not gathered, which is different from
    a file having none, and the caveats say so.
    """
    stamp = (now or datetime.now(UTC)).isoformat(timespec="seconds")
    rows: list[dict[str, Any]] = []
    name_only_matches = 0

    for ref in refs:
        owner_names, owner_emails = _actor_names(getattr(ref, "owners", None))
        modifier = getattr(ref, "last_modifying_user", None)
        basis = _matches(modifier, subject) if subject else None

        authored: list[Any] = []
        if subject and comments_by_file is not None:
            for comment in comments_by_file.get(ref.id, ()):
                how = _matches(getattr(comment, "author", None), subject)
                if how:
                    authored.append(comment)
                    if how == "display_name":
                        name_only_matches += 1
        if basis == "display_name":
            name_only_matches += 1

        row = {c: "" for c in COLUMNS}
        row.update({
            "file_id": ref.id,
            "name": _export.flatten(ref.name),
            "type": ref.type or "",
            "url": getattr(ref, "url", "") or "",
            "drive_id": getattr(ref, "drive_id", None) or "",
            "owner_names": _export.flatten(owner_names),
            "owner_emails": owner_emails,
            "created_time": _iso(getattr(ref, "created_time", None)),
            "modified_time": _iso(getattr(ref, "modified_time", None)),
            "last_modified_by": _export.flatten(
                getattr(modifier, "display_name", None) or "" if modifier else ""),
            "last_modified_by_email": getattr(modifier, "email", None) or "" if modifier else "",
            # `TRUE`/`FALSE` as text, and EMPTY when there is no subject to compare against -
            # the same three-state discipline `_apply.decision()` exists for. A blank read as
            # FALSE would assert the subject did not touch a file nobody asked about.
            "edited_last_by_subject": "" if not subject else ("TRUE" if basis else "FALSE"),
            "comments_by_subject": "" if not subject or comments_by_file is None
                                   else str(len(authored)),
            "last_comment_by_subject": _iso(max(
                (c.created_time for c in authored if getattr(c, "created_time", None)),
                default=None)),
            "matched_on": basis or "",
        })
        rows.append(row)

    inv = Inventory(columns=list(COLUMNS), rows=rows,
                    unreachable=list(unreachable or ()), generated_at=stamp, subject=subject)
    inv.caveats = _caveats(inv, subject=subject, comments_gathered=comments_by_file is not None,
                           name_only_matches=name_only_matches)
    return inv


def _caveats(inv: Inventory, *, subject: str | None, comments_gathered: bool,
             name_only_matches: int) -> list[str]:
    """What this snapshot cannot tell you. Written for a person, not a log.

    Every one of these is a limit somebody would otherwise discover by acting on the table and
    being wrong. The unreachable one is first because it is the one that changes a conclusion.
    """
    out: list[str] = []
    if inv.unreachable:
        out.append(
            f"{len(inv.unreachable)} of {len(inv.rows) + len(inv.unreachable)} files could NOT "
            f"be read by the account that ran this, and are listed separately with a reason. "
            f"They are not absent from the person's work - they are outside what this account "
            f"can see. Do not present this table as a complete footprint.")
    if subject:
        out.append(
            "`edited_last_by_subject` is Drive's LAST editor only. If somebody else edited a "
            "file after the subject did, the subject reads FALSE here. It answers 'did they "
            "touch it last', never 'did they ever touch it'.")
        if name_only_matches:
            out.append(
                f"{name_only_matches} match(es) were made on DISPLAY NAME because Drive "
                f"supplied no email address. A display name is neither unique nor stable; the "
                f"`matched_on` column says which basis was used for each row.")
        if not comments_gathered:
            out.append(
                "Comments were not gathered, so `comments_by_subject` is blank rather than "
                "zero. Blank means not checked.")
    out.append(
        "A snapshot, not a live view: correct as of `generated_at` and deliberately not "
        "updated. Reading any file's content still goes through the normal authorized call - "
        "an id in this table grants nothing.")
    return out

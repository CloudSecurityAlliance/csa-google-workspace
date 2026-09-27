"""Capability gating — the first of #82's two dimensions.

https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82

#82's settled requirement surface separates two independent things:

1. **Capability gating at all** — may this deployment create comments? trash files? share
   them? Each on or off, globally. *This module.*
2. **Per-URL scope** for each enabled capability — *and* which files. Still to come.

The composition rule is that **global is a ceiling and per-file grants narrow, never
widen**, so building dimension 1 first is not a half-measure: dimension 2 can only ever
subtract from what is allowed here.

Why that ordering matters in practice: it lets the destructive tools ship *off*. A default
install cannot trash or share anything before the per-file allowlist exists, which closes
the window that would otherwise open between shipping those tools and finishing #82.

**Enforcement is a `Backend` wrapper, not a check in the tool layer.** Every `Backend`
method takes `file_id` first (or, for the account axis, nothing), which is what makes a
uniform wrapper possible at all — and it means an embedder using the library directly gets
the same guarantee as one going through MCP. `read_only` is the precedent; this is its
fine-grained sibling.

**Fail closed.** `_GATES` must name every `Backend` method. An unlisted name raises rather
than delegating, so adding a method to the protocol without deciding its gate is a loud
failure at import/first-call, not a silent hole. `tests/test_policy.py` asserts the
coverage so it fails in CI instead.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import exceptions as exc
from .allowlist import Entry, Listing

log = logging.getLogger(__name__)

# --- the capabilities -------------------------------------------------------

COMMENT_CREATE = "comment.create"
COMMENT_REPLY = "comment.reply"
COMMENT_RESOLVE = "comment.resolve"
COMMENT_EDIT = "comment.edit"
COMMENT_DELETE = "comment.delete"
CONTENT_WRITE = "content.write"
# Destroying content, as against editing it. Separate from CONTENT_WRITE for the same reason
# FILE_TRASH is separate from FILE_UPDATE: an operator can reasonably permit editing and refuse
# destruction. And the asymmetry is real rather than tidy - deleting a spreadsheet tab or a
# paragraph range removes work with NO trash and NO undo through the API, unlike `trash_file`,
# which is recoverable for 30 days. Google keeps revision history, so a human can recover; an
# agent cannot, and the tool cannot offer to.
CONTENT_DELETE = "content.delete"
FILE_CREATE = "file.create"
FILE_UPDATE = "file.update"
FILE_TRASH = "file.trash"
FILE_SHARE = "file.share"

ALL_CAPABILITIES = (COMMENT_CREATE, COMMENT_REPLY, COMMENT_RESOLVE, COMMENT_EDIT,
                    COMMENT_DELETE, CONTENT_WRITE, CONTENT_DELETE, FILE_CREATE, FILE_UPDATE,
                    FILE_TRASH, FILE_SHARE)

# --- the default: EVERYTHING ON, and the documentation's job is how to narrow it ----------
#
# Reversed 2026-08-28 (v0.31.0). Until then the default was "everything reversible" and both
# allowlists failed closed, so an unconfigured install refused every operation. The reasons for
# reversing it are mostly already written in this repository:
#
#   * The README already told operators to set `CSA_GW_ALLOWLIST_READ="*"`, and explained why
#     the fine-grained alternative is not what anyone wants. The fail-closed default was
#     contradicted by our own documented happy path; what it reliably produced was a setup step.
#   * `THREAT_MODEL.md` §1 names Drive as the PRIMARY control layer and this one as "defense in
#     depth, deliberately narrow ... not the primary layer and not intended to be". A
#     deliberately-narrow secondary layer that bricks the tool on install is inconsistent with
#     its own stated role.
#   * Somebody installing a Google Workspace MCP server intends to do Google Workspace things.
#     A control every operator disables during setup is not a control; it is a support burden
#     that additionally teaches people to paste `*` without reading.
#
# AND THE ARGUMENT THAT MAKES IT COHERENT RATHER THAN A RETREAT: a capability we enable is not a
# permission we grant. Every call still executes as the authorizing user against Google's ACLs -
# `organizer` on a file where that user is merely a Commenter still cannot edit it, because the
# API returns 403 and nothing here changes that. This model is a CEILING BELOW DRIVE'S, never an
# expansion of it, so "everything on" means *subtract nothing; let Drive decide*.
#
# `file.share` is included. It was argued for exclusion - not on the get-work-done path, so
# enabling it removes no real friction, while being the only capability whose effect leaves the
# organisation and cannot be recalled. Overruled deliberately by the CINO: Drive owns sharing
# policy, and an organisation that cares has sharing restrictions, target audiences and DLP
# available there. Recorded because a default that was argued about is worth being able to find.
#
# WHAT DID NOT CHANGE: `PolicyBackend` still fails closed on an unlisted `Backend` method. That
# is a code-safety invariant, not a posture, and must not be simplified away alongside this.
#
# The recoverability ordering that used to draw this line still exists and still matters - it is
# what `CAPABILITY_NOTES` records and what orders the profiles above. It no longer decides what
# is ON, only what an operator is told when choosing what to switch OFF.
DEFAULT_ENABLED = frozenset(ALL_CAPABILITIES)

# Kept as a name because the docs, the config resource and the profile ladder all refer to "the
# three you cannot take back". They are no longer off by default; they are the three an operator
# most often wants to remove, and `organizer` is the only profile that includes them.
# `CONTENT_DELETE` joins these: deleting a tab takes every cell or paragraph in it, and unlike
# `FILE_TRASH` there is no 30-day bin. Revision history means a *person* can recover; nothing this
# library exposes can, which is the sense in which it is irreversible HERE.
IRREVERSIBLE = frozenset({COMMENT_EDIT, COMMENT_DELETE, CONTENT_DELETE, FILE_SHARE})

# Nothing is off by default any more (see above). Kept as an empty set rather than deleted,
# because it is part of the public surface and something may still ask "what is disabled?" - the
# honest answer is now "nothing, unless you said so". `IRREVERSIBLE` carries what this used to
# mean: the three an operator most often wants to remove.
DEFAULT_DISABLED: frozenset[str] = frozenset()

# What each capability lets an install do, and whether Google gives you a way to undo it.
#
# This lives HERE, beside the constants, because it was previously restated from memory by
# every surface that explains the policy - the README, the `csa-gw://help/configuration`
# resource, `describe_configuration` - and the copies had drifted apart. The help resource
# had `editor` able to "tidy comments" (it cannot: `comment.edit` and `comment.delete` are
# `full`) and put rename/move and trash under `full` (they are `editor`). A model reads that
# resource to explain a refusal, so a wrong copy there is worse than a wrong README: it
# becomes an answer given to a user with the server's authority behind it.
#
# The recoverability column is the same one the comment above draws the default line on. It
# is stated once and rendered, rather than retyped per surface.
CAPABILITY_NOTES: dict[str, tuple[str, str]] = {
    COMMENT_CREATE:  ("start a comment thread", "yes - delete it, or it stays visible"),
    COMMENT_REPLY:   ("reply to a thread", "yes - the reply can be deleted"),
    COMMENT_RESOLVE: ("resolve or reopen a thread", "yes - and either way it posts a visible reply"),
    # "edit" UNDERSTATES THIS AND THE UNDERSTATEMENT MATTERS. `content.write` includes
    # cell-level destruction: `clear_cells` empties a range, `update_cells` overwrites whatever
    # was there, and `replace_text` with an empty replacement blanks text. An operator reading
    # "edit" would not expect that, so it is spelled out.
    #
    # It stays in `content.write` deliberately (CINO, 2026-09-01). Blanking a cell is a
    # FUNDAMENTAL editing operation, not an advanced one - and withholding it does not prevent
    # the destruction, it just makes somebody write a placeholder value instead, which is worse:
    # a blank cell is obviously empty, `-` or `TBD` or `0` looks like data. The same reasoning
    # that put trashing under `writer` rather than higher up: withholding a reversible capability
    # produced irreversible litter in real Drives.
    CONTENT_WRITE:   ("edit content, INCLUDING blanking cells and overwriting what was there",
                      "yes - Drive revision history, which a human can restore from"),
    FILE_CREATE:     ("create a new file", "n/a - nothing that exists is touched"),
    # MOVING A FILE CHANGES WHO CAN SEE IT, and an operator granting `writer` should not have to
    # derive that from Drive's documentation (#311, T38). `update_file_metadata` forwards
    # `addParents`/`removeParents`, and a file inherits the ACL of the folder it sits in - so a
    # move grants or revokes access with no `file.share` and no permission change visible on the
    # file itself.
    #
    # Accepted rather than gated separately, because it is what Drive does and a human `writer`
    # can already do it through the UI; splitting it out would make this ladder diverge from the
    # Drive roles it deliberately mirrors. Drive's folder ACLs are the control.
    #
    # The reversibility answer is qualified for the same reason: moving it back restores the
    # parent, but it does not un-happen the access somebody had while it sat elsewhere.
    FILE_UPDATE:     ("rename or move a file - and MOVING IT CHANGES WHICH FOLDER'S SHARING IT "
                      "INHERITS, so it can grant or revoke access without touching permissions",
                      "the move, yes - move it back. The access it granted meanwhile, no"),
    FILE_TRASH:      ("put a file in the trash", "yes, 30 days - the owner can restore it"),
    COMMENT_EDIT:    ("edit an existing comment", "NO - Google keeps no visible edit history"),
    COMMENT_DELETE:  ("delete a comment", "NO - the soft delete strips content and author"),
    # STRUCTURAL destruction, which is the line that actually separates this from
    # `content.write` - not "destructive vs not", because writing is destructive too. Removing a
    # tab or a Docs range is unreachable from `content.write`; emptying cells is not (see above).
    #
    # The recoverability wording is deliberately the SAME as `content.write`'s, because the
    # mechanism is the same one. It previously read "NO through this API", which put it beside
    # `comment.delete` in a reader's mind - and those are not alike: Drive keeps no revision
    # history for comments at all, so a deleted comment is gone in a way a deleted range is not.
    CONTENT_DELETE:  ("delete a tab, or a range of document content - STRUCTURAL destruction, "
                      "which editing cannot reach",
                      "NO for an agent - there is no trash and no undo it can reach. A HUMAN "
                      "can restore from Drive revision history, which is what separates this "
                      "from deleting a comment: Drive keeps no revision history for comments at "
                      "all, so that one is gone for everybody"),
    FILE_SHARE:      ("share a file with someone else", "NO, in effect - a copy taken is not revocable"),
}

# Named capability sets, mirroring GOOGLE DRIVE'S OWN ROLES.
#
# Named as the Drive API names them - `reader`, `commenter`, `writer`, `fileOrganizer`,
# `organizer` - rather than with a vocabulary of our own. An operator already holds Google's
# model of who may do what to a file, because Google taught them and they use it daily. A more
# precise model sharing none of its words makes them hold two and map between them, and the
# mapping is where mistakes live.
#
# It is also externally validated in a way our own reasoning was not. The v0.21.0 rework drew
# the line on "can this be undone?" and got a better answer than the verb-alarm ordering it
# replaced - but that was one project's reasoning. Drive's roles are the same problem solved at
# enormous scale, and they agree on the point that matters: WRITER CANNOT SHARE. Google
# withholds sharing from Editor and reserves it for Manager and Owner.
#
# The API string is what the config accepts, because it is what `get_file_permissions` returns -
# so the word in the configuration and the word in a tool result are the same word. UI labels
# are documented and REDIRECTED (see `mcp/_config.py`), never silently accepted.
#
# Profiles cover *capabilities only*. The file allowlists are not profiled and never will be:
# which documents a deployment may touch is inherently specific to that deployment, and a
# named default for it would be a named default for "which of your files an agent may change".
# That is the one thing nobody else gets to decide.
#
# Spec: docs/superpowers/specs/2026-08-28-capability-model-mirrors-drive.md
PROFILES: dict[str, frozenset[str]] = {
    # Viewer. Read and report; may also obtain copies, exactly as Drive's Viewer may download.
    "reader": frozenset(),
    # Commenter. Additive only, and `resolve` leaves a visible reply rather than a silent flag.
    "commenter": frozenset({COMMENT_CREATE, COMMENT_REPLY, COMMENT_RESOLVE}),
    # Writer - Drive's "Editor" in My Drive, "Contributor" in a shared drive. Everything
    # reversible: content edits (revision history), new files, rename/move, and trash.
    #
    # DELIBERATELY WIDER THAN DRIVE'S WRITER. Drive's Writer cannot reorganize a shared drive or
    # delete from it; that constraint exists because Drive folders have owners and hierarchy,
    # while our "move" is a rename and our "trash" is the user's own bin. Narrowing to match
    # would undo a v0.21.0 decision made on evidence: without `file.trash` an agent that creates
    # a working file cannot clean up after itself, so litter accumulates in somebody's Drive
    # with the only tool that could tidy it switched off. Mirror the shape and the names; do not
    # import a constraint whose premise we do not share.
    "writer": frozenset({COMMENT_CREATE, COMMENT_REPLY, COMMENT_RESOLVE, CONTENT_WRITE,
                         FILE_CREATE, FILE_UPDATE, FILE_TRASH}),
    # fileOrganizer - Drive's "Content manager": contribute AND MANAGE content.
    #
    # This rung is what makes "may destroy comment history, may never share" expressible. Before
    # it, `full` bundled R1 destruction with R0 disclosure and that posture had no name.
    # `comment.edit` and `comment.delete` sit here on recoverability: Drive has NO comment-level
    # restore (verified), and the soft delete strips content AND author.
    # `content.delete` joins this rung, not `writer`, because it reaches what EDITING CANNOT:
    # removing a tab, or a range of a Doc. That is the honest line, and it is not the
    # recoverability line - Drive keeps revision history for both, so a human can restore either.
    #
    # It is NOT a bound on destruction generally, and the comment here used to claim it was:
    # *(A `writer` may therefore edit a document all day and never destroy part of one.)* False.
    # A `writer` holds `content.write`, and `update_cells` overwrites whatever was in the range
    # while `clear_cells` empties it - both measured. Withholding those would not prevent the
    # destruction, only make somebody write a placeholder that looks like data (CINO, 2026-09-01;
    # see tests/test_cell_destruction_is_content_write.py). What bounds content destruction is
    # the MODIFY allowlist, by file.
    "fileOrganizer": frozenset({COMMENT_CREATE, COMMENT_REPLY, COMMENT_RESOLVE, CONTENT_WRITE,
                                FILE_CREATE, FILE_UPDATE, FILE_TRASH,
                                COMMENT_EDIT, COMMENT_DELETE, CONTENT_DELETE}),
    # organizer - Drive's "Manager": files, folders, PEOPLE and settings. Adds the one action
    # whose effect leaves the organisation and cannot be recalled once a copy is taken.
    "organizer": frozenset(ALL_CAPABILITIES),
}

# Our earlier vocabulary, kept working. Identical sets, not approximations - `test_policy.py`
# asserts the frozensets are the same object-equal value, so an alias cannot drift into meaning
# something slightly different from what it aliases.
PROFILE_ALIASES: dict[str, str] = {
    "editor": "writer",     # what `writer` was called here before v0.31.0
    "full": "organizer",    # ditto, and `organizer` is still every capability
}

# Google's UI labels. NOT accepted as configuration values - a config with two spellings for
# every value is a config whose meaning depends on which vocabulary the author happened to know.
# They are recognised only so a refusal can name the right value instead of listing all five.
UI_LABELS: dict[str, str] = {
    "viewer": "reader",
    "contributor": "writer",
    "content manager": "fileOrganizer",
    "contentmanager": "fileOrganizer",
    "manager": "organizer",
    "owner": "organizer",   # the ceiling here; this library has no permanent delete
}


def resolve_profile(name: str) -> str:
    """Config spelling -> profile key, or `ValueError` naming the right word.

    Three outcomes, and the third is why this is a function rather than a dict lookup: an
    operator who writes `manager` has not made a typo, they have used Google's own UI label. A
    bare "unknown profile" would send them to the documentation to discover that the thing they
    already know is called something else here.
    """
    key = name.strip().lower()
    # Case-insensitively against the real keys, because one of them is camelCase.
    # `fileOrganizer` is Drive's own spelling and `key` is lowercased, so a plain `in PROFILES`
    # never matched it — an operator typing the documented name got "not a known profile".
    for canonical in PROFILES:
        if canonical.lower() == key:
            return canonical
    if key in PROFILE_ALIASES:
        return PROFILE_ALIASES[key]
    if key in UI_LABELS:
        target = UI_LABELS[key]
        extra = ("" if key != "owner" else
                 " (this library has no permanent delete, so `organizer` is the ceiling)")
        raise ValueError(
            f"{name!r} is Google's interface label for the {target!r} role. "
            f"Use {target!r}{extra}.")
    raise ValueError(
        f"{name!r} is not a known profile. Choose one of: "
        f"{', '.join(PROFILES)}. These are Google Drive's own role names — "
        f"Viewer, Commenter, Editor/Contributor, Content manager, Manager. "
        f"Or set CSA_GW_CAPABILITIES to an explicit list instead.")


READ = "read"
MODIFY = "modify"


@dataclass(frozen=True)
class Scope:
    """Which files one *kind* of access may touch: everything, or a named set.

    `all_files` and "an empty set" are deliberately different states. Empty means *nothing is
    permitted* — the fail-closed default for the MCP server — and `all_files` is a decision
    somebody typed as a literal `*`. Collapsing them into one representation is how a
    fail-closed default turns into a fail-open one during a refactor.
    """
    all_files: bool = False
    ids: frozenset[str] = frozenset()
    entries: tuple[Entry, ...] = field(default=(), repr=False)
    # Why this scope is empty, when it is. Carried so a denial can say *which* variable to set
    # and why it currently yields nothing — "not set" and "set but empty" behave identically
    # and have completely different fixes.
    reason: str | None = None

    @classmethod
    def everything(cls) -> Scope:
        return cls(all_files=True)

    @classmethod
    def nothing(cls, reason: str | None = None) -> Scope:
        return cls(all_files=False, reason=reason)

    @classmethod
    def from_listing(cls, listing: Listing) -> Scope:
        return cls(all_files=listing.all_files, ids=listing.file_ids,
                   entries=listing.entries)

    def allows(self, file_id: str) -> bool:
        return self.all_files or file_id in self.ids

    def describe(self) -> str:
        if self.all_files:
            return "every file"
        if not self.ids:
            return "no files"
        return f"{len(self.ids)} listed file(s)"


@dataclass(frozen=True)
class Gate:
    """What a `Backend` method needs in order to proceed.

    Both facts belong in one place because `_GATES` is the security contract: a reader
    should see, per method, which capability it costs *and* whether the file allowlist
    applies. `file_scoped=False` is for calls with no file to check — the account axis, and
    creation, which cannot damage a file that already exists.
    """
    capability: str | Callable[..., str] | None
    access: str = MODIFY            # READ or MODIFY — which allowlist applies
    file_scoped: bool = True        # False for the account axis, which has no file id


# A per-file read: no capability needed, but the read allowlist applies.
READS_FILE = Gate(capability=None, access=READ, file_scoped=True)
# A listing (the account axis). No file id to check, so the *results* are filtered instead.
READS_LISTING = Gate(capability=None, access=READ, file_scoped=False)


def _reply_gate(file_id: str, comment_id: str, content: Any = None,
                action: Any = None) -> str:
    """`create_reply` is two operations wearing one method name.

    Resolve and reopen are **action-replies**, never a PATCH — probe-verified, and the
    reason `resolve_comment` posts a reply at all. So the capability depends on the
    arguments, not the method: a gate keyed only on the name would let anyone who may reply
    also resolve, which is the difference between adding to a thread and closing it.
    """
    return COMMENT_RESOLVE if action else COMMENT_REPLY


# Which capability each Backend method needs. `None` means "a read, always allowed" — reads
# are deliberately ungated: #82 is about damage containment, not confidentiality, because
# the agent already sees whatever the user's credentials see. A callable is consulted with
# the call's own arguments, for methods whose capability depends on them.
_GATES: dict[str, Gate] = {
    # reads — never gated: #82 is damage containment, not confidentiality. The agent already
    # sees whatever the user's credentials see.
    # Who the credential belongs to. The ACCOUNT axis, not a file one - there is no file id to
    # check, which is what `READS_LISTING` means here; the name is about the axis, not about
    # returning a list. `_filter_listing` passes a result with no "files" key through untouched,
    # so nothing is filtered and nothing needs a special case.
    #
    # Ungated like every other read: #82 is damage containment, not confidentiality. Withholding
    # the caller's own address from the caller would contain nothing - they consented in a
    # browser that showed it to them - while removing the cheapest check against acting as the
    # wrong account.
    "get_about_user": READS_LISTING,
    "get_file_metadata": READS_FILE,
    "list_permissions": READS_FILE,
    # "Who is waiting for access?" has no write in it. Ungated like every other read, and
    # file-scoped like them: it discloses who has asked, which is disclosure about the file.
    "list_access_proposals": READS_FILE,
    # Which labels are on this file: a read, and file-scoped like every other read.
    "list_file_labels": READS_FILE,
    # What a label IS - its title, its fields, its choices. NOT file-scoped, because a label
    # definition belongs to the ORGANISATION rather than to any one file, so there is no file
    # to check against an allowlist. It is also the only call here that reaches a second Google
    # API (`drivelabels`), and it can only ever read: this library never requests the write
    # scope, so mislabelling is impossible rather than merely disabled.
    # A shared DRIVE is not a file, so the file allowlist has no id to match and
    # `READS_LISTING` is the honest gate - the same shape and the same reasoning as
    # `get_label_definition`, which T41 records as `file_scoped=False` on an org-level object.
    # Read-only: there is no `update_drive` here, deliberately. Drive-level restrictions bound
    # an entire drive and every file in it, which makes them the broadest control this library
    # could touch and the last one it should be able to change.
    "get_drive": READS_LISTING,
    "get_label_definition": READS_LISTING,
    "search_files": READS_LISTING,
    "list_comments": READS_FILE,
    "get_comment": READS_FILE,
    "export_file": READS_FILE,
    # A read, and file-scoped like every other read: handing over the bytes of an uploaded
    # file is the same disclosure as handing over the text of a Google one.
    "download_file": READS_FILE,
    "get_document": READS_FILE,
    "get_spreadsheet": READS_FILE,
    "get_sheet_notes": READS_FILE,
    "get_values": READS_FILE,
    "get_presentation": READS_FILE,
    # creation: nothing existing to damage, so not file-scoped. `copy_file` is the exception —
    # it reads a source, so that source must be in the READ scope. The copy it produces is a
    # new file and therefore not in the modify allowlist either, so copying cannot be used to
    # obtain a writable duplicate of something unwritable.
    "create_file": Gate(FILE_CREATE, MODIFY, file_scoped=False),
    "copy_file": Gate(FILE_CREATE, READ, file_scoped=True),
    # file lifecycle: all three are MODIFY and file-scoped, and all three are ON by default
    # since v0.31.0 - `DEFAULT_DISABLED` is empty, which is why naming it here was misleading
    # rather than merely stale. Renaming or moving a document somebody else relies on is disruptive
    # without being destructive; trashing is recoverable for 30 days; sharing is neither -
    # it is the only capability here that can move data OUT of the organisation, which is why
    # Google's own MCP server declines to expose it at all. Ours exposes it behind a
    # capability that must be named explicitly AND a file that must be listed for modify.
    "update_file_metadata": Gate(FILE_UPDATE, MODIFY),
    "trash_file": Gate(FILE_TRASH, MODIFY),
    "create_permission": Gate(FILE_SHARE, MODIFY),
    # Ungranting is the same authority as granting, so it shares the capability rather than
    # earning one: an operator who may hand out access may take it back. Splitting them would
    # create a configuration that can share and cannot un-share, which is strictly worse than
    # either extreme and is the state this library was in until #235.
    "update_permission": Gate(FILE_SHARE, MODIFY),
    "delete_permission": Gate(FILE_SHARE, MODIFY),
    # Accepting an access proposal GRANTS A PERMISSION, so it is `file.share` in disguise and
    # is gated as `file.share` - not as some gentler "administrative" capability, however much
    # "resolve a request" sounds like paperwork. The outbound authority is identical: somebody
    # who could not read this file now can, and a copy they take is not recallable.
    #
    # Google's own scope table is the empirical form of the same argument: `list` accepts the
    # `.readonly` scopes, `resolve` demands `drive` or `drive.file`.
    #
    # DENY runs through this gate too. That is deliberate, and it is the one direction worth
    # justifying: denying grants nothing, so gating it is strictly conservative. But `action`
    # is a runtime argument, so a capability that depended on it would be a gate whose answer
    # the CALLER chooses - and an operator who has switched `file.share` off has said this
    # server does not decide who gets access, which is a statement about the workflow and not
    # only about the grant. Refusing both keeps that promise legible.
    "resolve_access_proposal": Gate(FILE_SHARE, MODIFY),
    # Tabs. Adding one is a content write; DELETING one is `content.delete`, because it takes
    # every cell or paragraph in that tab with it and there is no trash and no API undo.
    "sheets_add_tab": Gate(CONTENT_WRITE, MODIFY),
    "docs_add_tab": Gate(CONTENT_WRITE, MODIFY),
    "sheets_delete_tab": Gate(CONTENT_DELETE, MODIFY),
    "docs_delete_tab": Gate(CONTENT_DELETE, MODIFY),
    # Deleting a paragraph range. Its own Backend method exists precisely so this gate can
    # differ from `docs_batch_update`'s - the generic batch method cannot tell a delete from an
    # edit, so a delete riding on it would have been ungatable apart from editing.
    "docs_delete_range": Gate(CONTENT_DELETE, MODIFY),
    # comment writes
    "create_comment": Gate(COMMENT_CREATE, MODIFY),
    "create_reply": Gate(_reply_gate, MODIFY),   # reply vs resolve/reopen — see above
    "update_comment": Gate(COMMENT_EDIT, MODIFY),
    "update_reply": Gate(COMMENT_EDIT, MODIFY),
    "delete_comment": Gate(COMMENT_DELETE, MODIFY),
    "delete_reply": Gate(COMMENT_DELETE, MODIFY),
    # content writes
    "docs_batch_update": Gate(CONTENT_WRITE, MODIFY),
    "sheets_values_update": Gate(CONTENT_WRITE, MODIFY),
    "sheets_values_append": Gate(CONTENT_WRITE, MODIFY),
    "sheets_values_clear": Gate(CONTENT_WRITE, MODIFY),
    "sheets_batch_update": Gate(CONTENT_WRITE, MODIFY),
    "slides_batch_update": Gate(CONTENT_WRITE, MODIFY),
    # API-impossible today; ApiBackend raises UnsupportedOperation. Gated anyway so a future
    # PlaywrightBackend does not arrive ungated.
    "accept_suggestion": Gate(CONTENT_WRITE, MODIFY),
    "create_cell_anchored_comment": Gate(COMMENT_CREATE, MODIFY),
}


@dataclass(frozen=True)
class Policy:
    """What this deployment may do: which capabilities, and which files for read vs modify.

    Three independent bounds, composing one way only — **each is a ceiling, none can widen
    another**. A capability absent from `enabled` cannot be reached by listing a file; a file
    absent from `modify` cannot be reached by enabling a capability; and a file absent from
    `read` cannot be reached at all.

    Reads and mutations are separated because they are different risks. The usual posture is
    `read=Scope.everything()` — matching what Google's and Anthropic's Drive servers do, since
    the agent already sees whatever the user's credentials see — with `modify` a short,
    reviewed list. Bounding what can be *broken* is the part that helps.

    `Policy.default()` is **permissive** on both scopes. That is deliberate and it is *not*
    the MCP server's default: this class is also the library's, and `Workspace.from_credentials`
    is called by a developer writing code who has already made a decision. The MCP server is
    configuration handed to a model — and since v0.31.0 it does **not** fail closed when
    nothing is configured: unset means every file and every capability. What fails closed is a
    list somebody *tried* to write, and an unlisted `Backend` method. Two artifacts, two
    threat models, but no longer two defaults — see `mcp/_config.py`.
    """
    enabled: frozenset[str]
    read: Scope = field(default_factory=Scope.everything)
    modify: Scope = field(default_factory=Scope.everything)

    @classmethod
    def default(cls) -> Policy:
        return cls(enabled=DEFAULT_ENABLED)

    @classmethod
    def of(cls, *capabilities: str) -> Policy:
        unknown = sorted(set(capabilities) - set(ALL_CAPABILITIES))
        if unknown:
            raise ValueError(f"unknown capabilities: {', '.join(unknown)}; "
                             f"known: {', '.join(ALL_CAPABILITIES)}")
        return cls(enabled=frozenset(capabilities))

    def scope_for(self, access: str) -> Scope:
        return self.read if access == READ else self.modify

    def allows(self, capability: str | None) -> bool:
        return capability is None or capability in self.enabled

    def with_scopes(self, *, read: Scope | None = None,
                    modify: Scope | None = None) -> Policy:
        return Policy(enabled=self.enabled, read=read or self.read,
                      modify=modify or self.modify)

    def with_enabled(self, *capabilities: str) -> Policy:
        """Widen the capability set. Only ever called by whoever *configures* the server,
        never in-band: an agent that can widen its own policy does not have one."""
        widened = Policy.of(*(self.enabled | set(Policy.of(*capabilities).enabled)))
        return Policy(enabled=widened.enabled, read=self.read, modify=self.modify)

    def without(self, *capabilities: str) -> Policy:
        return Policy(enabled=self.enabled - set(capabilities), read=self.read,
                      modify=self.modify)


class PolicyBackend:
    """A `Backend` that refuses operations its `Policy` does not permit.

    Composed through the documented `Workspace(backend=…)` seam:

        Workspace(PolicyBackend(ApiBackend(services), Policy.of(COMMENT_CREATE)))
    """

    def __init__(self, inner: Any, policy: Policy):
        self._inner = inner
        self._policy = policy

    @property
    def policy(self) -> Policy:
        return self._policy

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in _GATES:
            # Fail closed: an unlisted method is one whose gate nobody decided.
            raise exc.UnsupportedOperation(
                f"{name!r} has no capability gate declared in policy._GATES, so it is "
                f"refused. Add it there (with None for a read) rather than bypassing this.")
        gate = _GATES[name]
        inner = getattr(self._inner, name)

        def guarded(*args: Any, **kwargs: Any) -> Any:
            rule = gate.capability
            capability = rule(*args, **kwargs) if callable(rule) else rule
            if not self._policy.allows(capability):
                log.warning("policy denied %s: capability %r is disabled", name, capability)
                raise exc.ReadOnlyError(
                    f"the {capability!r} capability is disabled for this server, so {name} "
                    f"is refused. An operator enables it in configuration; it cannot be "
                    f"turned on from here.")

            scope = self._policy.scope_for(gate.access)
            if gate.file_scoped:
                file_id = kwargs.get("file_id") or (args[0] if args else None)
                if file_id is None:
                    # Fail closed: a file-scoped call we cannot attribute to a file is one
                    # the allowlist cannot check.
                    raise exc.UnsupportedOperation(
                        f"{name} is declared file-scoped but was called without a file id, "
                        f"so the allowlist cannot be applied. This is a bug.")
                if not scope.allows(file_id):
                    log.warning("policy denied %s on %s: outside the %s allowlist",
                                name, file_id, gate.access)
                    raise self._denied(name, file_id, gate.access, scope)
                return inner(*args, **kwargs)

            result = inner(*args, **kwargs)
            # A listing has no single file to check, so the *results* are filtered. Anything
            # outside the read scope is not merely unreadable — it must not be named either,
            # or search becomes a way to enumerate files the policy excludes.
            return self._filter_listing(name, result, scope)

        guarded.__name__ = name
        return guarded

    @staticmethod
    def _filter_listing(name: str, result: Any, scope: Scope) -> Any:
        if scope.all_files or not isinstance(result, dict) or "files" not in result:
            return result
        kept = [f for f in result["files"] if scope.allows(f.get("id", ""))]
        dropped = len(result["files"]) - len(kept)
        if dropped:
            log.warning("policy filtered %d result(s) from %s: outside the read allowlist",
                        dropped, name)
        return {**result, "files": kept}

    def _denied(self, name: str, file_id: str, access: str, scope: Scope) -> Exception:
        which = "CSA_GW_ALLOWLIST_READ" if access == READ else "CSA_GW_ALLOWLIST_MODIFY"
        if not scope.all_files and not scope.ids:
            why = scope.reason or f"no {access} allowlist is configured."
            detail = (f"nothing is permitted for {access}. {why} An operator sets {which} to a "
                      f"list of document URLs, or to `*` for unrestricted {access} access.")
        else:
            detail = (f"it is not in the {access} allowlist ({scope.describe()}). An operator "
                      f"adds the document's URL to {which}.")
        message = f"{name} is refused on file {file_id}: {detail} It cannot be changed from here."
        # A refused *read* is not a ReadOnlyError — nothing about writing is involved.
        return exc.AccessError(message) if access == READ else exc.ReadOnlyError(message)

    def __repr__(self) -> str:
        return (f"PolicyBackend(inner={type(self._inner).__name__}, "
                f"enabled={sorted(self._policy.enabled)}, "
                f"read={self._policy.read.describe()}, "
                f"modify={self._policy.modify.describe()})")

"""Structured-output shapes for tool results.

Plain dicts built by hand rather than re-exporting the domain models, for two reasons:
the models carry deliberately redacting `__repr__`s and mutation methods that mean nothing
over the wire, and the wire shape is a contract we control independently of the library's
internals. `author` is the display name only — email is usually absent from the API and is
not surfaced (SECURITY.md). Comment *content* is returned: the agent needs it, and the
redacted repr protects logs, not tool output.
"""
from __future__ import annotations

import re
from typing import Any, TypedDict

from .. import _context, _export
from ..comments import ANCHOR_FILE
from . import _untrusted


class ReplyOut(TypedDict):
    id: str
    author: str | None
    content: str | None
    created_time: str | None
    # Who this reply hands the thread to, if anyone. Reassignment on a reply is how a
    # thread changes hands, so this is not a duplicate of the comment's own assignee.
    assignee_email: str | None
    mentioned_emails: list[str]


class CommentOut(TypedDict):
    id: str
    author: str | None
    content: str | None
    resolved: bool
    created_time: str | None
    cell: str | None          # where DRIVE anchored it: A1 for anything created via the API
    tab: str | None           # which sheet that cell is on; None when it could not be resolved
    linked_cell: str | None   # the cell its deep link points at, if it has one
    # Whether the comment is about SOMETHING SPECIFIC rather than about the file as a whole.
    # NOT raw anchor presence - that was the bug in #372, where a comment carrying 244
    # characters of quoted text reported False and read as "no passage to look at".
    anchored: bool
    # WHICH of the four attachment states, for callers that need more than the boolean:
    # "file" (no anchor, no quote), "object" (anchor, no quote - an image or a cell),
    # "text" (both - the ordinary case), "quote_only" (quote, NO anchor - API-created, and
    # emphatically not file-level). Three measured 2026-09-02 from the editor, the fourth
    # 2026-09-03 from the API.
    anchor_state: str
    # THE ACTION ITEM (#398). `assignee_email` is set when a comment was assigned to
    # somebody — the one comment state that carries an obligation rather than an opinion,
    # and "which comments are assigned to me" is the question a reviewer actually asks.
    # `null` means unassigned, which is the common case.
    #
    # Read-only: Drive ACCEPTS an assignee at create, returns 200 and stores nothing
    # (measured 2026-09-03), so nothing here can assign a comment. Say that rather than
    # letting a caller conclude the field is merely unset.
    assignee_email: str | None
    # Addresses structurally @mentioned. Real addresses, unlike `author`, which is a
    # display name — so this is the better identity signal when it is present.
    mentioned_emails: list[str]
    # Present only when the caller asked for it; `null` when the comment has no passage
    # (file-level, or anchored to a non-text object). Off by default — the token cost is the
    # caller's to manage, and #358 asks for exactly that.
    context: ContextOut | None
    # The passage the comment CLAIMS to be attached to, from Drive's `quotedFileContent`. Not
    # evidence about the document: the field is written by whoever created the comment and
    # Google validates it against neither the document nor the anchor, so an API-created
    # comment can quote text the document never contained (measured 2026-09-03, #380). `None`
    # means
    # the comment is on the FILE rather than on a passage - a real and common state ("looks
    # good to me") - which is why it is not an empty string.
    #
    # It was modelled in the library and NOT exposed here, which is how a comment register
    # ended up missing the column somebody actually wants: a model could list twenty comments
    # on a draft and not say which paragraph any of them referred to. It stayed hidden because
    # `_inline.py` consumes it for read_file_content(includeComments), so the field looked used.
    quoted_text: str | None
    replies: list[ReplyOut]


class DocumentOut(TypedDict):
    id: str
    name: str
    type: str
    url: str


class FileMetadataOut(TypedDict):
    id: str
    name: str
    # `None` for anything this library cannot OPEN - a PDF, a .docx, a folder. The same answer
    # `FileRef.type` has always given for a search hit; inventing a type here would contradict
    # search, which deliberately returns these.
    type: str | None
    mime_type: str
    url: str
    snippet: str | None       # leading text, unless excludeContentSnippets - or unopenable
    # Bytes, for an UPLOADED file. `None` means NOT KNOWN - Drive omits it for native Google
    # files, which have no byte length until exported. Here so a caller can see that a file is
    # too large to download BEFORE trying: being refused beats an OOM, and not needing to be
    # refused beats both.
    size_bytes: int | None
    detail: str


class DownloadOut(TypedDict):
    content_base64: str
    mime_type: str
    size_bytes: int


class ActorOut(TypedDict):
    """A person Drive names on a file. `email` is the key to match on when present; a display
    name is neither unique nor stable, which is the same caveat comment authors carry."""
    display_name: str | None
    email: str | None
    me: bool


class FileRefOut(TypedDict):
    id: str
    name: str
    type: str | None          # None for a type this library cannot open (PDF, folder, Form)
    mime_type: str
    url: str
    modified_time: str | None
    created_time: str | None
    # `[]` means Drive reported no owners, which is the normal state for a file in a SHARED
    # DRIVE - the drive owns it. `null` means the call did not ask.
    owners: list[ActorOut] | None
    # The MOST RECENT editor only. It answers "who touched it last", never "did this person
    # ever edit it" - if A edited and B edited after, A does not appear here.
    last_modifying_user: ActorOut | None
    # Which shared drive the file is in; null for My Drive.
    drive_id: str | None


class FilesOut(TypedDict):
    files: list[FileRefOut]


class PermissionOut(TypedDict):
    id: str
    # `grantee_type`, not `type`. Everywhere else in this surface `type` is the DOCUMENT kind
    # - document / spreadsheet / presentation - and a model reads these outputs interleaved.
    # One field name carrying two unrelated vocabularies is a misreading waiting to happen,
    # and renaming it costs nothing before 1.0.0 and is impossible after.
    grantee_type: str         # user | group | domain | anyone
    role: str                 # reader | commenter | writer | fileOrganizer | organizer | owner
    display_name: str | None
    email: str | None         # the payload of this call, unlike elsewhere here
    domain: str | None
    can_write: bool
    is_public: bool


class PermissionsOut(TypedDict):
    permissions: list[PermissionOut]
    public: bool              # anyone-with-the-link; the thing worth noticing
    writers: int


class AccessProposalOut(TypedDict):
    id: str
    # The one identity Google vouches for here, and the field to act on. `requested_roles` is
    # what they ASKED for, which is not the same thing as what they should get.
    requester_email: str
    requested_roles: list[str]
    create_time: str | None
    # UNTRUSTED, and more sharply than anything else on this surface: written by somebody with
    # NO access to the file, reaching a model deciding whether to give them some. Returned
    # because a person triaging requests needs to read it - never because it is evidence.
    request_message: str | None


class UnreachableOut(TypedDict):
    """An id that went in and produced no row. **Never omitted** — a table of only the
    readable files reads as a complete footprint, and somebody handing over work would
    conclude the missing files do not exist."""
    file_id: str
    reason: str               # no_access | not_found | trashed | failed
    detail: str


class InventoryOut(TypedDict):
    """A dated snapshot of one person's document footprint. `rows` is what was reached;
    `unreachable` is what was not, and why."""
    columns: list[str]
    rows: list[dict[str, str]]
    unreachable: list[UnreachableOut]
    caveats: list[str]
    generated_at: str
    subject: str | None
    reached: int
    row_count: int
    destination: str
    csv: str | None
    sheet_id: str | None
    sheet_url: str | None
    written_path: str | None
    detail: str


class ContextOut(TypedDict):
    """The passage around a comment's anchor, and WHY it is that passage.

    `kind` is for branching, `note` is the sentence a person reads. Both, because a consumer
    switches on the rule that fired while a human wants the explanation — and with neither they
    receive a passage they did not select and cannot tell the feature from a bug.

    `text` marks the selection in place with `⟦…⟧`, so under-selection is visible at a glance:
    three words at the head of a long paragraph needs no computation to spot.
    """
    text: str
    kind: str            # paragraph | paragraphs | heading_and_following | table | table_row
    #                      | nearest_text | not_found | ambiguous
    note: str
    paragraph_index: int | None
    paragraph_total: int | None
    heading_path: list[str]
    truncated: bool
    # Where the candidates are when `kind == "ambiguous"`. Facts, so the caller can decide:
    # holding the comment text they can often tell which occurrence was meant, and we cannot.
    candidates: list[dict[str, Any]]


class NoteOut(TypedDict):
    """A Sheets cell note. NOT a comment: no author, no thread, and it cannot be replied to or
    resolved — so nothing in a reply-and-resolve workflow applies to it."""
    tab: str
    cell: str
    text: str


class ContractOut(TypedDict):
    version: str
    context_kinds: list[str]
    context_kinds_extensible: bool
    context_kinds_added_in: dict[str, str]
    anchor_states: list[str]
    export_columns_reported: list[str]
    export_columns_fillable: list[str]
    export_columns_added_in: dict[str, str]
    selection_markers: dict[str, str]
    renderings: dict[str, str]
    detail: str


class ProtectedRangeOut(TypedDict):
    protected_range_id: int | None
    tab: str | None
    a1_range: str | None
    description: str | None
    # THE field to read before calling this protection: a warning-only range shows a dialog and
    # then permits the edit anyway. `enforced` is the inverse, precomputed, because a caller
    # branching on `warning_only` gets the polarity backwards half the time.
    warning_only: bool
    enforced: bool
    requesting_user_can_edit: bool | None
    editors: list[str]
    domain_users_can_edit: bool | None


class ProtectedRangesOut(TypedDict):
    file_id: str
    ranges: list[ProtectedRangeOut]
    count: int
    detail: str


class RestrictionsOut(TypedDict):
    file_id: str
    # What somebody CONFIGURED. `None` means Drive did not say, never "unrestricted".
    copy_requires_writer_permission: bool | None
    writers_can_share: bool | None
    # What Drive will actually permit THIS user, after the flags, the ACL and any drive-level
    # policy. A different question from the two above, and usually the more useful one.
    can_edit: bool | None
    can_comment: bool | None
    can_share: bool | None
    can_copy: bool | None
    can_delete: bool | None
    can_read_revisions: bool | None
    drive_id: str | None
    detail: str


class SharedDriveOut(TypedDict):
    drive_id: str
    name: str | None
    drive_members_only: bool | None
    domain_users_only: bool | None
    copy_requires_writer_permission: bool | None
    sharing_folders_requires_organizer_permission: bool | None
    admin_managed_restrictions: bool | None
    download_restricted_for_readers: bool | None
    download_restricted_for_writers: bool | None
    detail: str


class NotesOut(TypedDict):
    notes: list[NoteOut]
    count: int
    detail: str


class TabOut(TypedDict):
    """A spreadsheet tab. `hidden` is the one that matters — a hidden tab still exists, still
    holds data, and still occupies its name."""
    title: str
    sheet_id: int | None
    index: int | None
    hidden: bool
    type: str | None


class TabsOut(TypedDict):
    tabs: list[TabOut]
    count: int
    # Stated rather than left to be counted, because a hidden tab is the one a caller misses.
    hidden_count: int


class DocumentTabOut(TypedDict):
    """A Doc tab. Addressed by `tab_id`, never by title — Docs permits duplicate titles."""
    title: str
    tab_id: str
    index: int | None
    nesting_level: int


class DocumentTabsOut(TypedDict):
    tabs: list[DocumentTabOut]
    count: int


class RangeOut(TypedDict):
    a1_range: str
    values: list[list[str]]
    rows: int


class AllowlistEntryOut(TypedDict):
    file_id: str
    line: int
    status: str               # ok | trashed | unreachable
    # What DRIVE calls the file, absent when nothing could be fetched. Never merged with
    # `reason`: one is evidence, the other is what the operator typed, and the mismatch
    # between them is the thing worth seeing.
    name: str | None
    type: str | None
    reason: str | None        # the operator's own `#` comment
    detail: str | None        # why unreachable


class AllowlistPreviewOut(TypedDict):
    scope: str                # "read" or "modify"
    # True means EVERY file the credentials can reach. `entries` is then empty because there is
    # no list - not because nothing is permitted, which is the opposite answer.
    unrestricted: bool
    entries: list[AllowlistEntryOut]
    ok: int
    dead: int


class AllowlistsPreviewOut(TypedDict):
    read: AllowlistPreviewOut
    modify: AllowlistPreviewOut
    dead_entries: int         # across both, so "is anything wrong?" is one field


class LabelFieldOut(TypedDict):
    id: str
    name: str | None          # None when the definition could not be read
    value_type: str
    values: list[str]


class LabelOut(TypedDict):
    id: str
    name: str | None
    fields: list[LabelFieldOut]
    # Present ONLY when the name could not be read, and it says which of two causes and how to
    # fix it. A model that sees `name: null` with no reason cannot tell "unnamed" from "we could
    # not look", and those are different answers to "is this document classified?".
    unresolved_reason: str | None


class LabelsOut(TypedDict):
    labels: list[LabelOut]
    # Explicit, because the dangerous misreading is "no names shown" -> "not classified".
    # `labelled` is true whenever the file carries any label, resolved or not.
    labelled: bool
    names_unavailable: bool


class AccessProposalsOut(TypedDict):
    proposals: list[AccessProposalOut]
    # A count, so "is anyone waiting?" is answerable without the model counting a list and
    # getting it wrong on an empty one.
    pending: int


class ConfigOut(TypedDict):
    """What this server may do. Reasons from the allowlist are deliberately absent — they are
    written for whoever reviews the configuration and may name people or unannounced work."""
    read_scope: str                    # "every file" | "no files" | "N listed file(s)"
    read_unrestricted: bool            # true when the scope is `*` — see readable_file_ids
    readable_file_ids: list[str]       # the listed ids; EMPTY when unrestricted, not "none"
    modify_scope: str
    modify_unrestricted: bool
    modifiable_file_ids: list[str]
    profile: str | None                # the CSA_GW_PROFILE name AS SET, if one is set
    # Whether that profile actually decided anything. True when CSA_GW_CAPABILITIES also set,
    # in which case the explicit list wins - and reporting only `profile` made this payload
    # contradict its own capability list (RR-005).
    profile_ignored: bool
    capability_source: str             # "profile" | "explicit" | "default"
    capabilities_enabled: list[str]    # permitted by policy — includes the library's surface
    capabilities_reachable: list[str]  # ...and actually usable through a tool in THIS server
    capabilities_unreachable: list[str]  # enabled but no tool here uses them
    capabilities_disabled: list[str]
    read_only: bool
    # Which Google Cloud project this deployment's OAuth client belongs to, or None when no
    # client is configured or it could not be read. Not a secret - every consent screen and
    # every 403 already carries it - and the one fact that distinguishes two deployments that
    # are otherwise configured identically. See `auth.client_project_id` (#480).
    client_project: str | None
    flavour: str                       # "full" | "google" | "claude"
    flavour_note: str                  # "" when full; otherwise what is hidden and why
    blocked_reason: str | None         # why something permits nothing, when it does
    server_version: str                # csa-google-workspace's own version
    # The environment, carried here and not only in `report_a_problem`, because this is the
    # tool a model calls after any refusal — so the facts a bug report needs end up in the
    # transcript as a side effect of ordinary use, rather than only when somebody thinks to
    # ask for a report. A conversation pasted into an issue then arrives complete.
    os: str                            # named as a person would: "macOS 26.6.2", "Windows 11"
    architecture: str
    python_version: str
    installed_via: str                 # pipx | pip (venv) | pip (shared environment) | source
    help_resource: str                 # the resource URI, for clients that surface resources
    help_tool: str                     # ...and the tool, for clients that do not


class SlideOut(TypedDict):
    index: int                        # 1-based, as a person counts slides
    shape_ids: list[str]              # text-capable shapes, for insert_slide_text
    text: str
    notes: str


class SlidesOut(TypedDict):
    slides: list[SlideOut]


class EditOut(TypedDict):
    file_id: str
    type: str
    occurrences_changed: int | None   # None where the operation has no natural count
    detail: str


class ResourceOut(TypedDict):
    uri: str
    content: str


class CommentsOut(TypedDict):
    comments: list[CommentOut]


class CommentExportOut(TypedDict):
    """A bulk comment register: flat rows, ordered columns, and what not to trust.

    `columns` is ordered so writing a spreadsheet is a loop. `rows` is one row per comment AND
    per reply with `reply_to` naming the thread - the lossless shape, since one-row-per-thread
    is a group-by away and the reverse is not. `caveats` is where the multi-tab ambiguity is
    stated rather than papered over.
    """
    columns: list[str]
    rows: list[dict]
    caveats: list[str]
    thread_count: int
    row_count: int
    file_id: str
    file_name: str
    file_type: str
    destination: str            # rows | csv | sheet | file
    csv: str | None             # destination="csv": the text, RFC 4180
    sheet_id: str | None        # destination="sheet"
    sheet_url: str | None       # destination="sheet": hand this to the user
    written_path: str | None    # destination="file"
    detail: str


class ActionRowOut(TypedDict):
    row: int                    # the SPREADSHEET row, header included - what a person navigates by
    thread_id: str
    replied: bool
    resolved: bool
    reopened: bool
    deleted: bool
    failed: bool
    detail: str


class ApplyActionsOut(TypedDict):
    """What a filled-in register did, or would do.

    `applied` false means nothing happened - that is the default, because the blast radius is
    somebody's review under their own name. `would_reply` / `would_resolve` are the dry run's
    answer; `replied` / `resolved` are the real one.
    """
    applied: bool
    replied: int
    resolved: int
    reopened: int
    deleted: int
    would_reply: int
    would_resolve: int
    would_reopen: int
    would_delete: int
    skipped: int
    failed: int
    rows: list[ActionRowOut]
    file_id: str
    file_name: str
    source: str
    detail: str


class CellCommentsOut(TypedDict):
    """`comments_by_cell` - the answer, plus how much to trust it. (D3)

    The XLSX export carries one `threadedComments` member per SHEET, and **since #290 the
    relationship graph is walked to recover which sheet that is**, so each comment carries a
    `tab`. Pass `tab=` to narrow the search to one sheet.

    `tab_ambiguous` therefore means something narrower than it used to: not "this workbook has
    several tabs" but "at least one comment in this result could not be placed on a tab". That
    happens when the graph could not be walked - a truncated export, an unusual archive - and
    it is reported rather than resolved, because a silently-wrong cell is worse than a stated
    uncertainty. `unplaced` counts them, so a caller can say how much of the answer is exact.
    """
    comments: list[CommentOut]
    tab_ambiguous: bool
    tabs: list[str]
    unplaced: int
    detail: str


class TextOut(TypedDict):
    text: str


class SuggestionOut(TypedDict):
    suggestion_id: str
    kind: str                         # insertion | deletion
    text: str
    # No `author`. The Docs API does not expose one, and a permanently-null field is an
    # invitation to attribute somebody's edit to nobody.


class SuggestionsOut(TypedDict):
    suggestions: list[SuggestionOut]
    # Carried in the RESULT, not only the tool description. A model reads a description once,
    # when choosing the tool, and then reads the result - so by the time it is composing
    # "shall I accept these?" the description is thousands of tokens behind it and this is
    # what is in front of it.
    can_accept_or_reject: bool
    detail: str


class AuthOut(TypedDict):
    status: str          # authorized | already_authorized | declined | timed_out
    detail: str


class WhoamiOut(TypedDict):
    """The signed-in account's own identity.

    **This module's header says an email address is not surfaced. That rule is about OTHER
    PEOPLE** - a comment author is a third party whose address this server has no business
    disclosing to a model (SECURITY.md, and #476 is the open question about authorship
    resolution). The address here is the CALLER'S OWN, read from `about.get` against their own
    credential; withholding it would tell a person nothing they could not learn by looking at
    the browser they just consented in, while removing the only cheap answer to "which account
    is this server acting as".

    That question is a safety question on this server, not a convenience one: with read and
    modify scope over every file the credentials can reach, including `file.share` and
    `file.trash`, a wrong-account token should be detectable BEFORE a write, not after. It is
    the case `authenticate(force=True)` exists for.

    `email_address` is `None` when Drive returned no `user` node - unknown, which is not the
    same as absent, and must not render as an empty address.
    """
    email_address: str | None
    display_name: str | None


class AuthStatusOut(TypedDict):
    """Five states, and the reason this is not a boolean is that three of them are not "no".

    `no_credential` - nothing usable is cached; this is a first login.
    `scope_short`   - a credential IS cached and IS valid, it just predates a scope this
                      deployment has since started requiring. The fix is a re-consent, not a
                      first login, and collapsing this into `no_credential` would say "you are
                      not logged in" about a credential sitting right there and working fine
                      for everything it was issued for.
    `ready`         - cached, complete, AND verified against Google. The detail names the
                      account, because that is what the check learned and it is worth seeing
                      before a write.
    `cached`        - cached and complete, and Google could NOT be asked - a timeout, a socket
                      error, a 500. The file is well formed; whether it still works is unknown,
                      and the detail says which. This is the state `ready` used to occupy while
                      claiming more than it knew (#510).
    `credential_rejected`
                    - Google refused it, carrying Google's own message. Distinct from
                      `no_credential` because the file IS there and IS well formed, so "log in,
                      you have no credential" would be a false description of the machine.

    `client_project` rides on every state: which Google Cloud project the configured OAuth
    client belongs to, or `None` if none is configured or it could not be read. See
    `auth.client_project_id` for the incident that made its absence worth fixing.
    """
    status: str                      # no_credential | scope_short | ready
    token_path: str
    client_project: str | None
    detail: str


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def reply_out(reply: Any) -> ReplyOut:
    return {
        "id": reply.id,
        "author": getattr(reply.author, "display_name", None) if reply.author else None,
        "content": reply.content,
        "created_time": _iso(reply.created_time),
        "assignee_email": getattr(reply, "assignee_email", None),
        "mentioned_emails": list(getattr(reply, "mentioned_emails", ()) or ()),
    }


# `...range=B2` at the end of a deep link this library appended. Read back out rather than
# remembered, so a comment fetched in a later session reports the same thing as one just made.
_LINKED_CELL = re.compile(r"[?&#]range=([A-Z]+[0-9]+)\b")


def comment_out(comment: Any) -> CommentOut:
    location = getattr(comment, "location", None)
    linked = _LINKED_CELL.search(comment.content or "")
    return {
        "id": comment.id,
        "author": getattr(comment.author, "display_name", None) if comment.author else None,
        "content": comment.content,
        "resolved": bool(comment.resolved),
        "created_time": _iso(comment.created_time),
        # Two different facts, and conflating them under one name misled an end-to-end run
        # into reporting the wrong cell to a user. `cell` is where DRIVE anchored the comment
        # -- which for anything created through the API is A1, always, because the API cannot
        # anchor a comment to a cell at all. `linked_cell` is the cell the deep link points
        # at, which is what somebody asked for.
        "cell": getattr(location, "cell", None) if location else None,
        # Which sheet `cell` is on. None means the sheet could not be resolved from the export,
        # NOT the first sheet - on a multi-tab workbook a default here would be a coin flip
        # presented as a fact.
        "tab": getattr(location, "tab", None) if location else None,
        "linked_cell": linked.group(1) if linked else None,
        "quoted_text": getattr(comment, "quoted_text", None),
        "anchored": bool(getattr(comment, "anchored", False)),
        "anchor_state": getattr(comment, "anchor_state", ANCHOR_FILE),
        "assignee_email": getattr(comment, "assignee_email", None),
        "mentioned_emails": list(getattr(comment, "mentioned_emails", ()) or ()),
        "context": None,
        "replies": [reply_out(r) for r in (comment.replies or [])],
    }


_NO_ACCEPT = (
    "Read-only: the Google Docs API has no accept or reject endpoint, so no tool here can "
    "apply or discard a suggestion. It has to be done in the document. Use "
    "read_file_content(suggestions=\"accepted\"|\"rejected\") to see what the document would "
    "say either way.")


def suggestions_out(found: list) -> SuggestionsOut:
    return {
        "suggestions": [{"suggestion_id": s.suggestion_id, "kind": s.kind, "text": s.text}
                        for s in found],
        "can_accept_or_reject": False,
        # Said even when the list is empty, because "nothing suggested" and "I could not
        # tell" are different answers and a bare `[]` does not distinguish them.
        "detail": (f"{len(found)} suggestion(s). " if found else "No suggestions. ") + _NO_ACCEPT,
    }


def document_out(doc: Any) -> DocumentOut:
    return {"id": doc.id, "name": doc.name, "type": doc.type, "url": doc.url}


SNIPPET_CHARS = 500


def permission_out(p: Any) -> PermissionOut:
    return {"id": p.id, "grantee_type": p.type, "role": p.role,
            "display_name": p.display_name,
            "email": p.email, "domain": p.domain, "can_write": p.can_write,
            "is_public": p.is_public}


def permissions_out(perms: list) -> PermissionsOut:
    """Rolls up the two facts a reviewer actually asks for, so the model does not have to
    derive them from the list and get it wrong."""
    return {"permissions": [permission_out(p) for p in perms],
            "public": any(p.is_public for p in perms),
            "writers": sum(1 for p in perms if p.can_write)}


def access_proposal_out(p: Any) -> AccessProposalOut:
    """`request_message` is capped here rather than at the boundary, because the cap is a
    judgement about THIS field: it is a note on a "Request access" click, so it is short by
    nature, and it is the only string on this surface written by somebody with no access to the
    file at all. Control characters are handled for every field at once in
    `_tools._base._errors`; see `mcp/_untrusted.py`."""
    message = p.request_message
    return {"id": p.id, "requester_email": p.requester_email,
            "requested_roles": p.requested_roles, "create_time": p.create_time,
            "request_message": _untrusted.capped(message) if message else message}


def access_proposals_out(proposals: list) -> AccessProposalsOut:
    return {"proposals": [access_proposal_out(p) for p in proposals],
            "pending": len(proposals)}


def inventory_out(inv: Any, *, destination: str) -> InventoryOut:
    """Everything but the payload. The destination-specific fields are filled by the tool."""
    return {"columns": inv.columns,
            # `rows` ONLY for destination="rows", the same lesson `export_comments` learned the
            # hard way: a file destination that also returned every row blew the response limit
            # AFTER writing the file correctly, so the call failed on work that had succeeded.
            "rows": inv.rows if destination == "rows" else [],
            "unreachable": [{"file_id": u["file_id"], "reason": u["reason"],
                             "detail": u.get("detail", "")} for u in inv.unreachable],
            "caveats": inv.caveats, "generated_at": inv.generated_at, "subject": inv.subject,
            "reached": inv.reached, "row_count": len(inv.rows), "destination": destination,
            "csv": None, "sheet_id": None, "sheet_url": None, "written_path": None,
            "detail": ""}


def context_out(ctx: Any, markers: bool = True) -> ContextOut | None:
    """A context that was ASKED FOR always explains itself, so `null` means only "not asked".

    This used to pass `None` straight through, reasoning that a comment with no quoted text has
    no passage and that inventing a `kind` "would imply a failure where there is simply no
    question". The first half is right and the conclusion was wrong: `null` was *also* what a
    caller got for an unsupported file type and for not requesting context at all, so one value
    carried "no question", "not supported" and "never looked". A consumer could not tell that
    the search had run.

    `KIND_NO_QUOTE` and `KIND_UNSUPPORTED` now say those two out loud. `None` survives only for
    the third, where the caller already knows the answer because they chose it.
    """
    if ctx is None:
        return None
    text = ctx.text
    if not markers:
        # #421: the markers are for a HUMAN reading a register. A consumer matching on text
        # has to strip them, and 60 of 76 honest quotes read as fabrications when somebody
        # did not know they were there. Stripped at the boundary so the caller never has to
        # know the characters - knowing them is the thing that was hard to discover.
        text = text.replace(_context.OPEN, "").replace(_context.CLOSE, "")
    return {"text": text, "kind": ctx.kind, "note": ctx.note,
            "paragraph_index": ctx.paragraph_index, "paragraph_total": ctx.paragraph_total,
            "heading_path": list(ctx.heading_path), "truncated": ctx.truncated,
            "candidates": [{"paragraph_index": i, "heading_path": list(p)}
                           for i, p in ctx.candidates]}


# WHEN each member arrived. Hand-maintained, and the only hand-maintained thing here - the
# members themselves are derived from the constants, so this maps them to a release rather than
# restating them. A consumer pinning a contract needs the DATE of a change, not just its
# presence: "did this appear after the version I tested against?" is the question.
# `tests/test_output_contract.py` fails if a member exists with no entry here.
CONTEXT_KIND_ADDED_IN = {
    "paragraph": "0.41.0", "paragraphs": "0.41.0", "heading_and_following": "0.41.0",
    "table": "0.41.0", "table_row": "0.41.0", "nearest_text": "0.41.0",
    "not_found": "0.41.0", "ambiguous": "0.41.0",
    "no_quote": "0.44.0", "unsupported": "0.44.0",
    "spanning": "0.48.0",
}
EXPORT_COLUMN_ADDED_IN = {
    "anchor_state": "0.43.0", "assigned_to": "0.47.0", "mentions": "0.47.0",
}

# WHICH TEXT each surface returns, because a consumer comparing one against another needs to
# know they are not interchangeable - and the answer is less alarming than it looks: there are
# TWO renderings, not three. `read_file_content` and `context` are the SAME one.
RENDERINGS = {
    "read_file_content":
        "docs-api-text: the Docs API's structured content walked and concatenated. No escaping, "
        "no emphasis markers.",
    "export_comments.context / list_comments(context=true).context":
        "docs-api-text PLUS the selection markers - the SAME rendering as read_file_content. "
        "Strip the two markers and it is a literal substring of it.",
    "download_file_content(exportMimeType='text/markdown')":
        "drive-export-markdown: Drive's own converter. DIFFERENT - it escapes punctuation "
        "(`=` becomes `\\=`) and adds emphasis markers. Do not compare this against the other "
        "two without normalising.",
}


def contract_out(version: str) -> ContractOut:
    """What shape this server's results take — readable at runtime rather than diffed.

    #422: a consumer pinned a contract file and it went stale in four days — one vocabulary
    member and two columns. Their refresh was "diff two real payloads and look carefully",
    which only catches a change after it has landed. This is the same information, asked for.
    """
    from ..comments import ANCHOR_STATES
    return {
        "version": version,
        "context_kinds": sorted(_context.KINDS),
        "context_kinds_extensible": True,
        "context_kinds_added_in": dict(CONTEXT_KIND_ADDED_IN),
        "anchor_states": sorted(ANCHOR_STATES),
        "export_columns_reported": list(_export.REPORTED),
        "export_columns_fillable": list(_export.ACTIONS) + list(_export.COMPLETED),
        "export_columns_added_in": dict(EXPORT_COLUMN_ADDED_IN),
        "selection_markers": {"open": _context.OPEN, "close": _context.CLOSE,
                              "appears_in": "context only"},
        "renderings": dict(RENDERINGS),
        "detail": (
            f"context_kind is an OPEN vocabulary with {len(_context.KINDS)} members today and "
            f"it WILL gain more - `spanning` arrived in 0.48.0 because a quote crossing a "
            f"paragraph boundary was being reported as absent from its own document. Degrade "
            f"on an unrecognised value rather than raising, or re-read this before upgrading. "
            f"The export column set grows the same way. And there are TWO text renderings, not "
            f"three: read_file_content and context are the same one."),
    }


def protected_ranges_out(file_id: str, ranges: list) -> ProtectedRangesOut:
    enforced = sum(1 for r in ranges if r.enforced)
    warning = len(ranges) - enforced
    if not ranges:
        detail = ("No protected ranges on this spreadsheet. Nothing here is protected by "
                  "GOOGLE, which is a different question from what this server's policy "
                  "permits - a range with no protection can still be refused by policy, and "
                  "policy can still be routed around by another client.")
    else:
        detail = (f"{len(ranges)} protected range(s): {enforced} ENFORCED, {warning} "
                  f"warning-only. A warning-only range shows a dialog and then PERMITS the "
                  f"edit - do not report it as protection. Enforcement is Google's and applies "
                  f"to every client, not just this server.")
    return {"file_id": file_id, "count": len(ranges), "detail": detail,
            "ranges": [{"protected_range_id": r.protected_range_id, "tab": r.tab_title,
                        "a1_range": r.a1_range, "description": r.description,
                        "warning_only": r.warning_only, "enforced": r.enforced,
                        "requesting_user_can_edit": r.requesting_user_can_edit,
                        "editors": list(r.editor_users) + list(r.editor_groups),
                        "domain_users_can_edit": r.domain_users_can_edit}
                       for r in ranges]}


def restrictions_out(file_id: str, r: Any, drive_id: str | None) -> RestrictionsOut:
    if r.unknown:
        detail = ("Drive returned NO restriction information for this file. That is not the "
                  "same as unrestricted - it means we could not read it, and reporting it as "
                  "absent would be the dangerous direction.")
    else:
        blocked = [n for n, v in (("copying", r.can_copy), ("sharing", r.can_share),
                                  ("editing", r.can_edit), ("commenting", r.can_comment))
                   if v is False]
        detail = (f"Drive will refuse: {', '.join(blocked)}." if blocked
                  else "Drive permits editing, commenting, sharing and copying for this user.")
        if r.writers_can_share is False:
            detail += (" writersCanShare=false: writers may NOT re-share this file, and that is "
                       "enforced by Drive against every client - stronger than this server's "
                       "own file.share gate, which binds only its own calls.")
    return {"file_id": file_id, "drive_id": drive_id, "detail": detail,
            "copy_requires_writer_permission": r.copy_requires_writer_permission,
            "writers_can_share": r.writers_can_share,
            "can_edit": r.can_edit, "can_comment": r.can_comment, "can_share": r.can_share,
            "can_copy": r.can_copy, "can_delete": r.can_delete,
            "can_read_revisions": r.can_read_revisions}


def shared_drive_out(d: Any) -> SharedDriveOut:
    on = [n for n, v in (("driveMembersOnly", d.drive_members_only),
                         ("domainUsersOnly", d.domain_users_only),
                         ("copyRequiresWriterPermission", d.copy_requires_writer_permission),
                         ("sharingFoldersRequiresOrganizerPermission",
                          d.sharing_folders_requires_organizer_permission))
          if v is True]
    detail = (f"Restrictions in force on this shared drive: {', '.join(on)}. These bound every "
              f"file in the drive and every client, so they can make an action impossible "
              f"regardless of how this server is configured." if on
              else "No drive-level restrictions are set on this shared drive.")
    return {"drive_id": d.id, "name": d.name, "detail": detail,
            "drive_members_only": d.drive_members_only,
            "domain_users_only": d.domain_users_only,
            "copy_requires_writer_permission": d.copy_requires_writer_permission,
            "sharing_folders_requires_organizer_permission":
                d.sharing_folders_requires_organizer_permission,
            "admin_managed_restrictions": d.admin_managed_restrictions,
            "download_restricted_for_readers": d.download_restricted_for_readers,
            "download_restricted_for_writers": d.download_restricted_for_writers}


def notes_out(notes: list) -> NotesOut:
    return {"notes": [{"tab": n.tab, "cell": n.cell, "text": n.text} for n in notes],
            "count": len(notes),
            "detail": (f"{len(notes)} cell note(s). Notes are NOT comments - they have no "
                       f"author, no thread, and cannot be replied to or resolved."
                       if notes else "No cell notes on this spreadsheet.")}


def tabs_out(details: list) -> TabsOut:
    return {"tabs": [{"title": d["title"], "sheet_id": d["sheet_id"], "index": d["index"],
                      "hidden": d["hidden"], "type": d["type"]} for d in details],
            "count": len(details),
            "hidden_count": sum(1 for d in details if d["hidden"])}


def document_tabs_out(tabs: list) -> DocumentTabsOut:
    return {"tabs": [{"title": t["title"], "tab_id": t["tab_id"], "index": t["index"],
                      "nesting_level": t["nesting_level"]} for t in tabs],
            "count": len(tabs)}


def allowlist_preview_out(scope_name: str, p: Any) -> AllowlistPreviewOut:
    return {"scope": scope_name, "unrestricted": p.unrestricted,
            "entries": [{"file_id": e.file_id, "line": e.line, "status": e.status,
                         "name": e.name, "type": e.type, "reason": e.reason,
                         "detail": e.detail} for e in p.entries],
            "ok": p.ok, "dead": p.dead}


def label_out(label: Any) -> LabelOut:
    return {"id": label.id, "name": label.name,
            "fields": [{"id": f.id, "name": f.name, "value_type": f.value_type,
                        "values": f.values} for f in label.fields],
            "unresolved_reason": label.unresolved_reason}


def labels_out(labels: list) -> LabelsOut:
    return {"labels": [label_out(one) for one in labels],
            "labelled": bool(labels),
            "names_unavailable": any(not one.resolved for one in labels)}


def _actor_out(actor: Any) -> ActorOut:
    return {"display_name": actor.display_name, "email": actor.email, "me": actor.me}


def file_ref_out(ref: Any) -> FileRefOut:
    owners = getattr(ref, "owners", None)
    modifier = getattr(ref, "last_modifying_user", None)
    return {"id": ref.id, "name": ref.name, "type": ref.type, "mime_type": ref.mime_type,
            "url": ref.url, "modified_time": _iso(ref.modified_time),
            "created_time": _iso(getattr(ref, "created_time", None)),
            # `is not None` rather than truthiness: `()` is a real answer (a shared-drive
            # file has no owners) and must not be reported as "not asked".
            "owners": [_actor_out(o) for o in owners] if owners is not None else None,
            "last_modifying_user": _actor_out(modifier) if modifier else None,
            "drive_id": getattr(ref, "drive_id", None)}


def file_ref_metadata_out(ref: Any, detail: str) -> FileMetadataOut:
    """Metadata for a file this library cannot open. No snippet: a snippet is extracted text,
    and there is none - omitting it silently would look like an empty document."""
    return {"id": ref.id, "name": ref.name, "type": None, "mime_type": ref.mime_type,
            "url": ref.url, "snippet": None,
            "size_bytes": getattr(ref, "size_bytes", None), "detail": detail}


def file_metadata_out(doc: Any, snippet: str | None) -> FileMetadataOut:
    # None throughout: a native Google file has no `size` in Drive, and `Document` does not
    # carry one. Stating it explicitly rather than omitting the key, so the shape is uniform.
    return {"id": doc.id, "name": doc.name, "type": doc.type, "mime_type": doc.mime_type,
            "url": doc.url, "snippet": snippet, "size_bytes": None,
            "detail": f"A Google {doc.type}. read_file_content will read its text."}


class ProblemReportOut(TypedDict):
    """What to put in a bug report, and where to put it.

    Carries no file ids, no titles and no paths: this is written to be pasted into a PUBLIC
    issue tracker. Scopes are described by shape ("every file", "3 files") rather than by
    content, which is the opposite of `ConfigOut` and deliberate — see `_environment`.
    """
    report: str                 # ready to paste, markdown
    issues_url: str
    new_issue_url: str          # prefilled, and already carries `label`
    label: str                  # the tracker label this will be filed under
    server_version: str
    python_version: str
    os: str
    architecture: str
    mcp_sdk_version: str | None
    installed_via: str
    profile: str | None
    read_only: bool
    read_scope: str
    modify_scope: str
    authorized: bool
    checklist: list[str]


class FileUpdateOut(TypedDict):
    """The result of a metadata change: what the file is now, not what it was."""
    id: str
    name: str | None
    # `None` means the response did not carry parents, NOT that the file has none - a file
    # with no parents is not a state Drive has. Hard-coded to `[]` until v0.21.0.
    parents: list[str] | None


class TrashOut(TypedDict):
    id: str
    name: str | None
    trashed: bool             # false after untrash, so one shape serves both directions


class DemonstrationStepOut(TypedDict):
    step: int
    tool: str
    do: str                    # what happens, in a sentence
    why: str | None            # worth saying out loud while doing it
    available: bool            # false when the current policy will refuse it
    applies_to: str            # document | spreadsheet | presentation | account | cleanup


class DemonstrationOut(TypedDict):
    """A plan to carry out, not a result. See `_tools/demo.py` for why it does not just run."""
    steps: list[DemonstrationStepOut]
    unavailable: list[str]     # what this policy refuses, said once per reason
    cleanup_possible: bool     # false -> the user deletes the files by hand; say so FIRST
    creates_real_files: bool
    unattended_command: str
    narrated_command: str
    advice: str


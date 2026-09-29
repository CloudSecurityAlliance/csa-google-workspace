"""Comment domain model. Normalizes the Drive API's quirks (all probe-verified):
`resolved` absent ⇒ False; deleted strips content+author; author email often absent."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from .exceptions import DetachedError, ReadOnlyError

if TYPE_CHECKING:
    from .backend import Backend


@dataclass
class Location:
    """Where a spreadsheet comment is anchored.

    `cell`/`row`/`col` come from the comment's own `ref` in the XLSX export. `tab` comes from
    walking that export's relationship graph, which is a separate and more fragile operation -
    so the two degrade independently, and a comment can know its cell but not its sheet.

    **`tab is None` means the sheet could not be resolved. It never means the first sheet.** On
    a multi-tab workbook a default here would be a coin flip presented as a fact, which is the
    failure this library treats as the dangerous direction (see `labels.py` for the same rule
    about an unresolvable label name).
    """
    cell: str
    row: int
    col: int
    tab: str | None = None


def parse_time(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@dataclass
class Author:
    display_name: str
    email: str | None
    is_me: bool
    photo_url: str | None

    @classmethod
    def from_api(cls, d: dict | None) -> Author | None:
        if not d:
            return None
        return cls(display_name=d.get("displayName", ""), email=d.get("emailAddress"),
                   is_me=bool(d.get("me", False)), photo_url=d.get("photoLink"))

    def __repr__(self) -> str:
        # Redacted: omit email (PII) — see #49. display_name kept for identification.
        return f"Author(display_name={self.display_name!r}, is_me={self.is_me})"


@dataclass
class Reply:
    id: str
    author: Author | None
    content: str | None
    html_content: str | None
    action: str | None
    deleted: bool
    created_time: datetime | None
    modified_time: datetime | None
    # WHO this reply is addressed to, structurally (#398). Replies carry both fields -
    # MEASURED 2026-09-03, and `quotedFileContent` is REFUSED on a reply, so the reply
    # resource is not simply a narrower comment. Reassigning on a reply is how a thread
    # changes hands, so a reply's assignee is not a curiosity.
    assignee_email: str | None = None
    mentioned_emails: tuple[str, ...] = ()
    # Injected by Comment/CommentCollection after construction to enable mutation.
    # The cast(..., None) defaults let these carry their true (non-Optional) types
    # while still defaulting to None for the from_api() construction path.
    _backend: Backend = field(default=cast("Backend", None), repr=False, compare=False)
    _file_id: str = field(default=cast(str, None), repr=False, compare=False)
    _comment_id: str = field(default=cast(str, None), repr=False, compare=False)
    _read_only: bool = field(default=False, repr=False, compare=False)

    @classmethod
    def from_api(cls, d: dict) -> Reply:
        return cls(id=d["id"], author=Author.from_api(d.get("author")),
                   content=d.get("content"), html_content=d.get("htmlContent"),
                   action=d.get("action"), deleted=bool(d.get("deleted", False)),
                   created_time=parse_time(d.get("createdTime")),
                   modified_time=parse_time(d.get("modifiedTime")),
                   assignee_email=d.get("assigneeEmailAddress"),
                   mentioned_emails=tuple(d.get("mentionedEmailAddresses") or ()))

    def __repr__(self) -> str:
        # Redacted: omit content/html_content (document text) and the email fields, which
        # are collaborator PII exactly as `Author.email` is (#49, #398). Counts only.
        n = len(self.content) if self.content else 0
        return (f"Reply(id={self.id!r}, action={self.action!r}, deleted={self.deleted}, "
                f"content_chars={n}, assigned={self.assignee_email is not None}, "
                f"mentions={len(self.mentioned_emails)})")

    def edit(self, text: str) -> None:
        if self._backend is None:
            raise DetachedError("this Reply was built via Reply.from_api() and has no backend; "
                                "obtain it via a Comment on a Workspace to mutate it")
        if self._read_only:
            raise ReadOnlyError("workspace is read_only; cannot edit a reply")
        d = self._backend.update_reply(self._file_id, self._comment_id, self.id, text)
        self.content = d.get("content"); self.html_content = d.get("htmlContent")

    def delete(self) -> None:
        if self._backend is None:
            raise DetachedError("this Reply was built via Reply.from_api() and has no backend; "
                                "obtain it via a Comment on a Workspace to mutate it")
        if self._read_only:
            raise ReadOnlyError("workspace is read_only; cannot delete a reply")
        self._backend.delete_reply(self._file_id, self._comment_id, self.id)
        self.deleted = True; self.content = None; self.html_content = None; self.author = None


# The four ways a comment can be attached, as a CLOSED vocabulary (#372). A boolean cannot
# carry this: `anchor` present and `quoted_text` present are INDEPENDENT signals, so there are
# four combinations and only three of them were ever documented.
#
# Closed for the same reason `_context.KINDS` is - a fifth member should be a deliberate act
# with a measurement behind it, not an accident. All four are measured:
# `experiments/docs-anchor-states/` for the editor-created three, and
# `experiments/api-created-comment-states/` for `quote_only`, which only the API can produce.
ANCHOR_FILE = "file"              # neither: about the document, not a passage
ANCHOR_OBJECT = "object"          # anchor, no quote: an image, a drawing, a cell
ANCHOR_TEXT = "text"              # both: the ordinary case
ANCHOR_QUOTE_ONLY = "quote_only"  # quote, no anchor: API-created, and NOT file-level
ANCHOR_STATES = frozenset({ANCHOR_FILE, ANCHOR_OBJECT, ANCHOR_TEXT, ANCHOR_QUOTE_ONLY})


@dataclass
class Comment:
    id: str
    author: Author | None
    content: str | None
    html_content: str | None
    quoted_text: str | None
    anchor: str | None
    location: Location | None
    resolved: bool
    deleted: bool
    created_time: datetime | None
    modified_time: datetime | None
    # WHO the comment is addressed to, structurally rather than as prose (#398).
    #
    # `assignee_email` is the ACTION ITEM: the one comment state carrying an obligation
    # rather than an opinion, and "which comments are assigned to me" is the question a
    # reviewer actually asks. `mentioned_emails` carries real addresses, which is the
    # identity signal `author.email` lacks - it is usually absent even when requested.
    #
    # Both are read-only here, and that is Drive's doing rather than a choice: MEASURED
    # 2026-09-03, `comments.create` ACCEPTS either in the body, returns 200, and stores
    # NEITHER. Third instance of that pattern in one day, after `keepForever` and the
    # anchor trap. Also measured: `fields=*` OMITS both, so the wildcard is not a way to
    # discover them - they must be named in the mask, which is what `_CF` now does.
    assignee_email: str | None = None
    mentioned_emails: tuple[str, ...] = ()
    replies: list[Reply] = field(default_factory=list)
    # Injected by CommentCollection after construction (see Reply for the cast rationale).
    _backend: Backend = field(default=cast("Backend", None), repr=False, compare=False)
    _file_id: str = field(default=cast(str, None), repr=False, compare=False)
    _read_only: bool = field(default=False, repr=False, compare=False)

    @property
    def anchor_state(self) -> str:
        """WHICH of the four ways this comment is attached - one of `ANCHOR_STATES`.

        `anchor` presence and `quoted_text` presence are independent, so there are **four**
        combinations. Three were measured from the editor on 2026-09-02
        (`experiments/docs-anchor-states/`); the fourth was measured from the API on
        2026-09-03 (`experiments/api-created-comment-states/`) after a consumer hit it on real
        material (#372):

        | `anchor` | `quoted_text` | state | means |
        |---|---|---|---|
        | absent | absent | `ANCHOR_FILE` | about the document, not a passage |
        | present | absent | `ANCHOR_OBJECT` | an image, a drawing, a cell - a location, nothing to quote |
        | present | present | `ANCHOR_TEXT` | the ordinary case |
        | absent | **present** | `ANCHOR_QUOTE_ONLY` | **quoted a passage, recorded no anchor** |

        **`ANCHOR_QUOTE_ONLY` is API-created and is NOT file-level.** The editor cannot produce
        it - it snaps a bare caret to the enclosing word and refuses to comment on empty space
        - so it only ever arrives from a tool writing through the Drive API. And such a tool is
        usually *right* to omit the anchor: an API-supplied anchor is stored verbatim and then
        treated as un-anchored by the editors (measured 2026-07-09), so a client that knows
        this drops the useless field and keeps the quote. Expect this state on any file another
        tool has written to; it is not corruption.

        **The anchor itself is opaque** - `kix.…` in Docs, `workbook-range` in Sheets - so it
        is a key, not a coordinate, and deliberately not exposed. This property is the part of
        it that carries information.

        A quote is counted as present when it is non-empty rather than merely non-`None`.
        Drive OMITS an absent field rather than sending it empty (measured), so `""` should not
        occur - and if it ever does it carries no passage, so it must not read as one. (This is
        safe here in a way the rule in CLAUDE.md's invariant 9 warns about elsewhere: a quote
        is a string, never a legitimate `False` or `0`.)
        """
        has_quote = bool(self.quoted_text)
        if self.anchor is not None:
            return ANCHOR_TEXT if has_quote else ANCHOR_OBJECT
        return ANCHOR_QUOTE_ONLY if has_quote else ANCHOR_FILE

    @property
    def anchored(self) -> bool:
        """Whether this comment is about SOMETHING SPECIFIC, rather than about the file.

        Equivalently `anchor_state != ANCHOR_FILE`. Use `anchor_state` when the difference
        between the three attached states matters.

        **This is not raw anchor presence, and the change was a bug fix (#372).** It used to be
        `self.anchor is not None`, which reported `False` on comments carrying 244 characters of
        quoted text that this library's own context resolution placed in a specific paragraph -
        4 of 90 threads on one real document. `False` reads as *"there is no passage to look
        at"*, so a consumer skipped exactly the comments a reviewer had quoted at length. Silent,
        and in the confident direction.

        Raw anchor presence was the wrong thing to expose because **nothing can act on it**: the
        anchor string is opaque and not published, and the one anchor-derived feature here
        (`context`) locates by quoted text instead - which is why three of those four rows
        resolved to a paragraph correctly even while this field denied they had one.

        What it answers now is the question callers ask: *is there a passage this is about?*
        """
        return self.anchor_state != ANCHOR_FILE

    @classmethod
    def from_api(cls, d: dict) -> Comment:
        quoted = (d.get("quotedFileContent") or {}).get("value")
        return cls(
            id=d["id"], author=Author.from_api(d.get("author")),
            content=d.get("content"), html_content=d.get("htmlContent"),
            quoted_text=quoted, anchor=d.get("anchor"), location=None,
            resolved=bool(d.get("resolved", False)),   # absent ⇒ False (MEASURED)
            deleted=bool(d.get("deleted", False)),
            created_time=parse_time(d.get("createdTime")),
            modified_time=parse_time(d.get("modifiedTime")),
            assignee_email=d.get("assigneeEmailAddress"),
            mentioned_emails=tuple(d.get("mentionedEmailAddresses") or ()),
            replies=[Reply.from_api(r) for r in d.get("replies", [])],
        )

    def __repr__(self) -> str:
        # Redacted: omit content/quoted_text/html_content (document text) and author email — see #49.
        n = len(self.content) if self.content else 0
        return (f"Comment(id={self.id!r}, resolved={self.resolved}, deleted={self.deleted}, "
                f"replies={len(self.replies)}, content_chars={n}, "
                f"quoted={self.quoted_text is not None}, "
                f"assigned={self.assignee_email is not None}, "
                f"mentions={len(self.mentioned_emails)})")

    def _guard(self):
        if self._backend is None:
            raise DetachedError("this Comment was built via Comment.from_api() and has no backend; "
                                "obtain it via Workspace.open(...).comments to mutate it")
        if self._read_only:
            raise ReadOnlyError("workspace is read_only; cannot mutate comments")

    def reply(self, text: str) -> Reply:
        self._guard()
        r = Reply.from_api(self._backend.create_reply(self._file_id, self.id, content=text))
        self._attach_reply(r)
        self.replies.append(r)
        return r

    def resolve(self, text: str = "") -> Reply:
        self._guard()
        r = Reply.from_api(self._backend.create_reply(
            self._file_id, self.id, content=text or None, action="resolve"))
        self._attach_reply(r)
        self.replies.append(r)
        self.resolved = True
        return r

    def reopen(self, text: str = "") -> Reply:
        self._guard()
        r = Reply.from_api(self._backend.create_reply(
            self._file_id, self.id, content=text or None, action="reopen"))
        self._attach_reply(r)
        self.replies.append(r)
        self.resolved = False
        return r

    def edit(self, text: str) -> None:
        self._guard()
        d = self._backend.update_comment(self._file_id, self.id, text)
        self.content = d.get("content"); self.html_content = d.get("htmlContent")

    def delete(self) -> None:
        self._guard()
        self._backend.delete_comment(self._file_id, self.id)
        self.deleted = True; self.content = None; self.html_content = None; self.author = None
        for r in self.replies:
            r.deleted = True
            r.content = None
            r.html_content = None
            r.author = None

    def _attach_reply(self, r: Reply) -> None:
        r._backend = self._backend; r._file_id = self._file_id
        r._comment_id = self.id; r._read_only = self._read_only


class CommentCollection:
    """Lazy, filterable view of a file's comments."""

    def __init__(self, backend, file_id: str, read_only: bool, locate=None):
        self._backend = backend
        self._file_id = file_id
        self._read_only = read_only
        self._locate = locate

    def _wrap(self, d: dict) -> Comment:
        c = Comment.from_api(d)
        c._backend = self._backend
        c._file_id = self._file_id
        c._read_only = self._read_only
        for r in c.replies:
            r._backend = self._backend; r._file_id = self._file_id
            r._comment_id = c.id; r._read_only = self._read_only
        if self._locate is not None:
            c.location = self._locate(d)
        return c

    def all(self, include_deleted: bool = False) -> list[Comment]:
        return [self._wrap(d) for d in self._backend.list_comments(
            self._file_id, include_deleted=include_deleted)]

    def get(self, comment_id: str, *, include_deleted: bool = False) -> Comment:
        """One comment thread. `include_deleted` is needed to fetch a soft-deleted one, which
        Drive otherwise reports as missing - the record survives, the visibility does not."""
        return self._wrap(self._backend.get_comment(self._file_id, comment_id,
                                                    include_deleted=include_deleted))

    def filter(self, *, resolved: bool | None = None, author: str | None = None,
               since: datetime | None = None, include_deleted: bool = False) -> list[Comment]:
        smt = None
        if since is not None:
            aware = since if since.tzinfo else since.replace(tzinfo=UTC)
            smt = aware.astimezone(UTC).isoformat().replace("+00:00", "Z")
        raw = self._backend.list_comments(self._file_id, include_deleted=include_deleted,
                                          start_modified_time=smt)
        out = []
        for d in raw:
            c = self._wrap(d)
            if resolved is not None and c.resolved != resolved:
                continue
            if author is not None and not (c.author and (c.author.email == author
                                                          or c.author.display_name == author)):
                continue
            out.append(c)
        return out

    def __iter__(self):
        return iter(self.all())

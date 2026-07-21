"""Comment domain model. Normalizes the Drive API's quirks (all probe-verified):
`resolved` absent ⇒ False; deleted strips content+author; author email often absent."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


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
    def from_api(cls, d: dict | None) -> "Author | None":
        if not d:
            return None
        return cls(display_name=d.get("displayName", ""), email=d.get("emailAddress"),
                   is_me=bool(d.get("me", False)), photo_url=d.get("photoLink"))


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

    @classmethod
    def from_api(cls, d: dict) -> "Reply":
        return cls(id=d["id"], author=Author.from_api(d.get("author")),
                   content=d.get("content"), html_content=d.get("htmlContent"),
                   action=d.get("action"), deleted=bool(d.get("deleted", False)),
                   created_time=parse_time(d.get("createdTime")),
                   modified_time=parse_time(d.get("modifiedTime")))


@dataclass
class Comment:
    id: str
    author: Author | None
    content: str | None
    html_content: str | None
    quoted_text: str | None
    anchor: str | None
    location: object | None  # populated in the Sheets cell-mapping phase; None here
    resolved: bool
    deleted: bool
    created_time: datetime | None
    modified_time: datetime | None
    replies: list[Reply] = field(default_factory=list)
    # set by CommentCollection; enable mutation (Task 5)
    _backend: object = field(default=None, repr=False, compare=False)
    _file_id: str | None = field(default=None, repr=False, compare=False)
    _read_only: bool = field(default=False, repr=False, compare=False)

    @classmethod
    def from_api(cls, d: dict) -> "Comment":
        quoted = (d.get("quotedFileContent") or {}).get("value")
        return cls(
            id=d["id"], author=Author.from_api(d.get("author")),
            content=d.get("content"), html_content=d.get("htmlContent"),
            quoted_text=quoted, anchor=d.get("anchor"), location=None,
            resolved=bool(d.get("resolved", False)),   # absent ⇒ False (MEASURED)
            deleted=bool(d.get("deleted", False)),
            created_time=parse_time(d.get("createdTime")),
            modified_time=parse_time(d.get("modifiedTime")),
            replies=[Reply.from_api(r) for r in d.get("replies", [])],
        )


class CommentCollection:
    """Lazy, filterable view of a file's comments."""

    def __init__(self, backend, file_id: str, read_only: bool):
        self._backend = backend
        self._file_id = file_id
        self._read_only = read_only

    def _wrap(self, d: dict) -> "Comment":
        c = Comment.from_api(d)
        c._backend = self._backend
        c._file_id = self._file_id
        c._read_only = self._read_only
        return c

    def all(self, include_deleted: bool = False) -> list["Comment"]:
        return [self._wrap(d) for d in self._backend.list_comments(
            self._file_id, include_deleted=include_deleted)]

    def get(self, comment_id: str) -> "Comment":
        return self._wrap(self._backend.get_comment(self._file_id, comment_id))

    def filter(self, *, resolved: bool | None = None, author: str | None = None,
               since: "datetime | None" = None, include_deleted: bool = False) -> list["Comment"]:
        smt = since.isoformat().replace("+00:00", "Z") if since else None
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

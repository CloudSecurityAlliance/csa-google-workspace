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

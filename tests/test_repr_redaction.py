"""repr() of the domain models must not leak document text or author email into logs
(audit #27 / #49). Multi-tenant servers acting on users' behalf log these objects; the
default dataclass repr would dump other users' content and contact info.
"""
from csa_google_workspace.comments import Author, Comment, Reply
from csa_google_workspace.suggestions import Suggestion

RAW = {
    "id": "c1",
    "content": "SECRET salary figures",
    "quotedFileContent": {"value": "QUOTED confidential"},
    "author": {"displayName": "Jane Doe", "emailAddress": "jane@corp.example"},
    "replies": [{"id": "r1", "content": "PRIVATE reply note",
                 "author": {"emailAddress": "bob@corp.example"}}],
}


def test_author_repr_omits_email_keeps_name():
    r = repr(Author(display_name="Jane Doe", email="jane@corp.example", is_me=False, photo_url="http://p"))
    assert "jane@corp.example" not in r
    assert "http://p" not in r
    assert "Jane Doe" in r


def test_comment_repr_omits_content_quoted_and_email():
    r = repr(Comment.from_api(RAW))
    for leak in ("SECRET salary figures", "QUOTED confidential", "jane@corp.example"):
        assert leak not in r, f"repr leaked {leak!r}: {r}"
    assert "c1" in r and "content_chars=" in r


def test_reply_repr_omits_content():
    r = repr(Reply.from_api(RAW["replies"][0]))
    assert "PRIVATE reply note" not in r
    assert "r1" in r


def test_suggestion_repr_omits_text():
    r = repr(Suggestion(suggestion_id="s1", kind="insertion", text="CONFIDENTIAL draft"))
    assert "CONFIDENTIAL draft" not in r
    assert "s1" in r

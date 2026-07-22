from datetime import datetime, timezone

from csa_google_workspace.comments import Comment, Reply, parse_time

FRESH = {  # never-resolved comment: no `resolved` key, no author email
    "id": "c1", "content": "hi", "htmlContent": "hi", "deleted": False,
    "createdTime": "2026-07-20T23:05:59.479Z", "modifiedTime": "2026-07-20T23:05:59.479Z",
    "author": {"displayName": "Kurt", "me": True}, "replies": [],
}
RESOLVED = {**FRESH, "id": "c2", "resolved": True,
            "replies": [{"id": "r1", "action": "resolve", "content": "", "deleted": False,
                         "createdTime": "2026-07-20T23:06:00Z", "author": {"displayName": "Kurt", "me": True}}]}
DELETED = {"id": "c3", "deleted": True, "createdTime": "2026-07-20T23:05:00Z",
           "modifiedTime": "2026-07-20T23:06:00Z", "replies": []}  # no content, no author


def test_parse_time_handles_zulu():
    assert parse_time("2026-07-20T23:05:59.479Z") == datetime(2026, 7, 20, 23, 5, 59, 479000, tzinfo=timezone.utc)
    assert parse_time(None) is None


def test_resolved_absent_is_false():
    assert Comment.from_api(FRESH).resolved is False


def test_resolved_true_when_present():
    c = Comment.from_api(RESOLVED)
    assert c.resolved is True
    assert c.replies[0].action == "resolve"


def test_author_email_optional_and_is_me():
    a = Comment.from_api(FRESH).author
    assert a.display_name == "Kurt" and a.is_me is True and a.email is None


def test_deleted_comment_tolerates_missing_author_and_content():
    c = Comment.from_api(DELETED)
    assert c.deleted is True and c.author is None and c.content is None


def test_deleted_reply_tolerates_missing_author_and_content():
    r = Reply.from_api({"id": "r9", "deleted": True, "createdTime": "2026-07-20T23:06:00Z"})
    assert r.deleted is True
    assert r.author is None
    assert r.content is None


def test_quoted_text_extracted():
    d = {**FRESH, "quotedFileContent": {"mimeType": "text/html", "value": "the text"}}
    assert Comment.from_api(d).quoted_text == "the text"

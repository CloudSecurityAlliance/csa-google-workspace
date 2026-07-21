import pytest
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace import exceptions as exc

DOC = "application/vnd.google-apps.document"
FILES = {"f": {"id": "f", "name": "F", "mimeType": DOC, "webViewLink": "https://x/document/d/f/edit"}}


def be():
    return FakeBackend(FILES)


def test_create_then_list_and_resolved_absent():
    b = be()
    c = b.create_comment("f", "hello")
    assert c["content"] == "hello" and "resolved" not in c   # fresh comment: no resolved key
    assert [x["id"] for x in b.list_comments("f")] == [c["id"]]


def test_reply_and_resolve_flips_parent():
    b = be(); c = b.create_comment("f", "q")
    b.create_reply("f", c["id"], content="a reply")
    b.create_reply("f", c["id"], action="resolve")            # content-less action reply
    assert b.get_comment("f", c["id"])["resolved"] is True
    b.create_reply("f", c["id"], action="reopen")
    assert b.get_comment("f", c["id"])["resolved"] is False


def test_soft_delete_strips_and_hides():
    b = be(); c = b.create_comment("f", "bye")
    b.delete_comment("f", c["id"])
    assert b.list_comments("f") == []                          # hidden by default
    got = b.list_comments("f", include_deleted=True)[0]
    assert got["deleted"] is True and "content" not in got and "author" not in got


def test_missing_comment_raises_not_found():
    with pytest.raises(exc.NotFoundError):
        be().get_comment("f", "nope")

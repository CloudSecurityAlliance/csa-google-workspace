import pytest
from datetime import datetime, timezone
from csa_google_workspace import Workspace, exceptions as exc
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
FILES = {"f": {"id": "f", "name": "F", "mimeType": DOC, "webViewLink": "https://x/document/d/f/edit"}}


def open_doc(read_only=False):
    return Workspace(FakeBackend(FILES), read_only=read_only).open("f")


def test_create_and_list_comments():
    d = open_doc()
    c = d.create_comment("hello")
    assert c.content == "hello" and c.resolved is False
    assert [x.id for x in d.comments.all()] == [c.id]


def test_get_by_id():
    d = open_doc(); c = d.create_comment("x")
    assert d.comments.get(c.id).id == c.id


def test_filter_by_resolved():
    d = open_doc()
    a = d.create_comment("open one")
    b = d.create_comment("to resolve")
    d._backend.create_reply("f", b.id, action="resolve")
    unresolved = d.comments.filter(resolved=False)
    assert [c.id for c in unresolved] == [a.id]


def test_create_comment_blocked_when_read_only():
    d = open_doc(read_only=True)
    with pytest.raises(exc.ReadOnlyError):
        d.create_comment("nope")


def test_filter_by_since():
    d = open_doc()
    d.create_comment("c")
    # FakeBackend comments carry a fixed ~2026 modifiedTime: a past `since` includes, a future one excludes
    assert len(d.comments.filter(since=datetime(2020, 1, 1, tzinfo=timezone.utc))) == 1
    assert d.comments.filter(since=datetime(2030, 1, 1, tzinfo=timezone.utc)) == []

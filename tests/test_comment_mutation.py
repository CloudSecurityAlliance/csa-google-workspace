import pytest

from csa_google_workspace import Workspace
from csa_google_workspace import exceptions as exc
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
FILES = {"f": {"id": "f", "name": "F", "mimeType": DOC, "webViewLink": "https://x/document/d/f/edit"}}


def doc(read_only=False):
    return Workspace(FakeBackend(FILES), read_only=read_only).open("f")


def test_resolve_flips_in_place_and_appends_reply():
    c = doc().create_comment("q")
    r = c.resolve()                       # content-less
    assert c.resolved is True
    assert r.action == "resolve" and c.replies[-1].action == "resolve"


def test_reopen_flips_back():
    c = doc().create_comment("q"); c.resolve()
    c.reopen()
    assert c.resolved is False


def test_reply_appends_in_place():
    c = doc().create_comment("q")
    r = c.reply("thanks")
    assert r.content == "thanks" and c.replies[-1].id == r.id


def test_edit_updates_content_in_place():
    c = doc().create_comment("old")
    c.edit("new")
    assert c.content == "new"


def test_delete_marks_deleted_and_strips_in_place():
    c = doc().create_comment("bye")
    c.delete()
    assert c.deleted is True and c.content is None and c.author is None


def test_mutation_blocked_when_read_only():
    d = doc(read_only=True)
    # create a comment via the backend directly (bypass the read-only create), then try to mutate
    raw = FakeBackend(FILES).create_comment("f", "x")
    c = d.comments._wrap(raw)
    c._read_only = True
    with pytest.raises(exc.ReadOnlyError):
        c.resolve()


def test_reply_edit_and_delete_in_place():
    d = doc()
    c = d.create_comment("q")
    r = c.reply("orig")
    r.edit("edited")
    assert r.content == "edited"
    r.delete()
    assert r.deleted is True
    assert r.content is None
    assert r.author is None


def test_reply_mutation_blocked_when_read_only():
    d = doc()
    c = d.create_comment("q")
    r = c.reply("x")
    r._read_only = True
    with pytest.raises(exc.ReadOnlyError):
        r.edit("nope")
    with pytest.raises(exc.ReadOnlyError):
        r.delete()


def test_replies_from_collection_are_mutable():
    d = doc()
    c = d.create_comment("q")
    c.reply("orig")
    refetched = d.comments.get(c.id)          # replies come via _wrap
    refetched.replies[0].edit("via collection")
    assert refetched.replies[0].content == "via collection"


def test_delete_also_strips_replies_in_place():
    d = doc()
    c = d.create_comment("bye")
    c.reply("a reply")
    c.delete()
    assert c.replies[0].deleted is True
    assert c.replies[0].content is None
    assert c.replies[0].author is None

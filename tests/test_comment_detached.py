"""A Comment/Reply built via from_api() (not obtained through a Workspace) has no
backend injected. Mutating it must raise a clear typed error, not a bare
AttributeError on None (audit finding #5)."""
import pytest

from csa_google_workspace import exceptions as exc
from csa_google_workspace.comments import Comment, Reply

RAW_COMMENT = {"id": "c1", "author": {"displayName": "A"}, "content": "hi", "replies": []}
RAW_REPLY = {"id": "r1", "content": "hi"}


def test_detached_comment_edit_raises_detached_error():
    with pytest.raises(exc.DetachedError):
        Comment.from_api(RAW_COMMENT).edit("nope")


def test_detached_comment_reply_raises_detached_error():
    with pytest.raises(exc.DetachedError):
        Comment.from_api(RAW_COMMENT).reply("nope")


def test_detached_comment_delete_raises_detached_error():
    with pytest.raises(exc.DetachedError):
        Comment.from_api(RAW_COMMENT).delete()


def test_detached_reply_edit_raises_detached_error():
    with pytest.raises(exc.DetachedError):
        Reply.from_api(RAW_REPLY).edit("nope")


def test_detached_reply_delete_raises_detached_error():
    with pytest.raises(exc.DetachedError):
        Reply.from_api(RAW_REPLY).delete()


def test_detached_error_is_a_workspace_error():
    assert issubclass(exc.DetachedError, exc.CsaWorkspaceError)

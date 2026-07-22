import pytest

from csa_google_workspace import Workspace
from csa_google_workspace import exceptions as exc
from csa_google_workspace.backend import FakeBackend

PRES = "application/vnd.google-apps.presentation"
META = {"p": {"id": "p", "name": "P", "mimeType": PRES, "webViewLink": "https://x/presentation/d/p/edit"}}


def slides(read_only=False):
    b = FakeBackend(META)
    return Workspace(b, read_only=read_only).open("p"), b


def test_replace_text_builds_deckwide_replaceAllText():
    p, b = slides()
    result = p.replace_text("old", "new")
    assert b._writes == [("p", "slides", [{"replaceAllText": {
        "containsText": {"text": "old", "matchCase": True}, "replaceText": "new"}}])]
    assert isinstance(result, int) and result == 0  # FakeBackend returns {} -> defaults to 0


def test_replace_text_match_case_false():
    p, b = slides()
    p.replace_text("old", "new", match_case=False)
    assert b._writes == [("p", "slides", [{"replaceAllText": {
        "containsText": {"text": "old", "matchCase": False}, "replaceText": "new"}}])]


def test_batch_update_records():
    p, b = slides()
    p.batch_update([{"createShape": {}}])
    assert ("p", "slides", [{"createShape": {}}]) in b._writes


def test_insert_text_builds_shape_addressed_insertText():
    p, b = slides()
    p.insert_text("box1", "hello", index=3)
    assert b._writes == [("p", "slides", [{"insertText": {
        "objectId": "box1", "text": "hello", "insertionIndex": 3}}])]


def test_insert_text_defaults_to_index_zero():
    p, b = slides()
    p.insert_text("box1", "hi")
    assert b._writes[0][2][0]["insertText"]["insertionIndex"] == 0


def test_writes_blocked_when_read_only():
    p, _ = slides(read_only=True)
    for call in (lambda: p.replace_text("a", "b"), lambda: p.batch_update([{}]),
                 lambda: p.insert_text("box1", "x")):
        with pytest.raises(exc.ReadOnlyError):
            call()


def test_replace_text_handles_empty_replies_list():
    """Backend returns empty replies list instead of missing key or default."""
    class FakeBackendEmptyReplies(FakeBackend):
        def slides_batch_update(self, file_id, requests):
            self._writes.append((file_id, "slides", requests))
            return {"replies": []}

    b = FakeBackendEmptyReplies(META)
    p = Workspace(b).open("p")
    result = p.replace_text("old", "new")
    assert result == 0  # Should fall back to 0, not crash on IndexError

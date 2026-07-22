import pytest
from csa_google_workspace import Workspace, exceptions as exc
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


def test_writes_blocked_when_read_only():
    p, _ = slides(read_only=True)
    for call in (lambda: p.replace_text("a", "b"), lambda: p.batch_update([{}])):
        with pytest.raises(exc.ReadOnlyError):
            call()

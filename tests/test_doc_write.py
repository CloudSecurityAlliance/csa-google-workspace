import pytest
from csa_google_workspace import Workspace, exceptions as exc
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
META = {"d": {"id": "d", "name": "D", "mimeType": DOC, "webViewLink": "https://x/document/d/d/edit"}}


def doc(read_only=False, document=None):
    b = FakeBackend(META, documents={"d": document or {"body": {"content": [{"endIndex": 10}]}}})
    return Workspace(b, read_only=read_only).open("d"), b


def test_replace_text_builds_replaceAllText():
    d, b = doc()
    result = d.replace_text("old", "new")
    assert b._writes == [("d", "docs", [{"replaceAllText": {
        "containsText": {"text": "old", "matchCase": True}, "replaceText": "new"}}])]
    assert isinstance(result, int) and result == 0  # FakeBackend returns {} -> defaults to 0


def test_replace_text_match_case_false():
    d, b = doc()
    d.replace_text("old", "new", match_case=False)
    assert b._writes == [("d", "docs", [{"replaceAllText": {
        "containsText": {"text": "old", "matchCase": False}, "replaceText": "new"}}])]


def test_insert_text_builds_insertText_at_index():
    d, b = doc()
    d.insert_text("hi", at=5)
    assert b._writes == [("d", "docs", [{"insertText": {"location": {"index": 5}, "text": "hi"}}])]


def test_append_text_inserts_before_final_newline():
    d, b = doc(document={"body": {"content": [{"endIndex": 42}]}})
    d.append_text("tail")
    assert b._writes == [("d", "docs", [{"insertText": {"location": {"index": 41}, "text": "tail"}}])]


def test_delete_range_builds_deleteContentRange():
    d, b = doc()
    d.delete_range(3, 7)
    assert b._writes == [("d", "docs", [{"deleteContentRange": {"range": {"startIndex": 3, "endIndex": 7}}}])]


def test_writes_blocked_when_read_only():
    d, _ = doc(read_only=True)
    for call in (lambda: d.replace_text("a", "b"), lambda: d.insert_text("x", 1),
                 lambda: d.append_text("x"), lambda: d.delete_range(1, 2),
                 lambda: d.batch_update([{}])):
        with pytest.raises(exc.ReadOnlyError):
            call()

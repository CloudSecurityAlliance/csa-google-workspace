import pytest
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
META = {"f": {"id": "f", "name": "F", "mimeType": DOC, "webViewLink": "https://x/document/d/f/edit"}}


def be():
    return FakeBackend(META)


def test_docs_batch_update_records():
    b = be()
    b.docs_batch_update("f", [{"insertText": {"location": {"index": 1}, "text": "hi"}}])
    assert b._writes == [("f", "docs", [{"insertText": {"location": {"index": 1}, "text": "hi"}}])]


def test_sheets_values_update_records_and_updates_fixture():
    b = be()
    b.sheets_values_update("f", "Sheet1!A1", [["x", "y"]])
    assert ("f", "sheets_values_update", "Sheet1!A1", [["x", "y"]], "RAW") in b._writes
    assert b.get_values("f", "Sheet1!A1") == [["x", "y"]]      # readback reflects the write


def test_sheets_values_clear_records_and_clears_fixture():
    b = be()
    b.sheets_values_update("f", "Sheet1!A1", [["x"]])
    b.sheets_values_clear("f", "Sheet1!A1")
    assert b.get_values("f", "Sheet1!A1") == []


def test_slides_batch_update_records():
    b = be()
    b.slides_batch_update("f", [{"replaceAllText": {}}])
    assert ("f", "slides", [{"replaceAllText": {}}]) in b._writes

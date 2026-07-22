import pytest

from csa_google_workspace import exceptions as exc
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
META = {"f": {"id": "f", "name": "F", "mimeType": DOC, "webViewLink": "https://x/document/d/f/edit"}}


def be():
    return FakeBackend(
        META,
        documents={"f": {"title": "F", "body": {"content": []}}},
        spreadsheets={"f": {"sheets": [{"properties": {"sheetId": 0, "title": "Sheet1"}}]}},
        values={("f", "Sheet1!A1:B2"): [["a", "b"], ["c", "d"]]},
        presentations={"f": {"slides": []}},
        exports={("f", "application/pdf"): b"%PDF-1.4 fake"},
    )


def test_get_document_returns_fixture():
    assert be().get_document("f")["title"] == "F"


def test_get_document_missing_raises():
    with pytest.raises(exc.NotFoundError):
        be().get_document("nope")


def test_get_values_returns_grid_and_absent_is_empty():
    b = be()
    assert b.get_values("f", "Sheet1!A1:B2") == [["a", "b"], ["c", "d"]]
    assert b.get_values("f", "Sheet1!Z1:Z9") == []


def test_get_spreadsheet_and_presentation():
    b = be()
    assert b.get_spreadsheet("f")["sheets"][0]["properties"]["title"] == "Sheet1"
    assert be().get_presentation("f") == {"slides": []}


def test_export_returns_bytes():
    assert be().export_file("f", "application/pdf") == b"%PDF-1.4 fake"

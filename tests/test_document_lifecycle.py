"""Test Document base functionality: reload(), export(), and related."""
from csa_google_workspace import Workspace, exceptions as exc
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"
PRES = "application/vnd.google-apps.presentation"


def test_reload_sheet_clears_cell_map_cache():
    """Sheet.reload() should clear the internal cell map cache."""
    backend = FakeBackend(
        {"f": {"id": "f", "name": "F", "mimeType": SHEET, "webViewLink": "https://x"}},
        spreadsheets={"f": {"sheets": [{"properties": {"sheetId": 0, "title": "Sheet1"}}]}},
        exports={("f", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"): b"fake xlsx"},
    )
    ws = Workspace(backend)
    sheet = ws.open("f")
    # Set cache to a sentinel
    sheet._cell_map_cache = {"sentinel": True}
    # reload() should clear it
    sheet.reload()
    assert sheet._cell_map_cache is None


def test_export_file_pdf():
    """Document.export() should return file bytes for requested MIME type."""
    backend = FakeBackend(
        {"f": {"id": "f", "name": "F", "mimeType": DOC, "webViewLink": "https://x"}},
        exports={("f", "application/pdf"): b"%PDF-fake-content"}
    )
    ws = Workspace(backend)
    doc = ws.open("f")
    pdf_bytes = doc.export("application/pdf")
    assert pdf_bytes == b"%PDF-fake-content"


def test_export_missing_raises_not_found():
    """Exporting a file with no export fixture should raise NotFoundError."""
    backend = FakeBackend(
        {"f": {"id": "f", "name": "F", "mimeType": DOC, "webViewLink": "https://x"}},
        exports={}
    )
    ws = Workspace(backend)
    doc = ws.open("f")
    try:
        doc.export("application/pdf")
        assert False, "should have raised NotFoundError"
    except exc.NotFoundError:
        pass  # expected


def test_reload_doc_base_does_nothing():
    """Document base reload() is a no-op (subclasses override as needed)."""
    backend = FakeBackend(
        {"f": {"id": "f", "name": "F", "mimeType": DOC, "webViewLink": "https://x"}},
        documents={"f": {"title": "F", "body": {"content": []}}}
    )
    ws = Workspace(backend)
    doc = ws.open("f")
    # Should not raise
    doc.reload()

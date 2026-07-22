"""Cross-type end-to-end integration tests against REAL Google.

For each of Doc / Sheet / Slides: create a throwaway file, seed content, drive the
whole library stack (open -> verify type -> read content -> full comment lifecycle),
and trash the file. Supersedes the earlier Doc-only comment/content live tests.

Gated: skipped unless CSA_GW_INTEGRATION=1. Also needs CSA_GW_CLIENT_SECRETS pointing
at an OAuth client-secrets JSON (a cached token avoids re-consent). Nothing here runs
at import/collection time.

    CSA_GW_INTEGRATION=1 CSA_GW_CLIENT_SECRETS=path/to/client_secret.json \
        pytest tests/integration/test_all_types_live.py -v
"""
import contextlib
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CSA_GW_INTEGRATION") != "1",
    reason="set CSA_GW_INTEGRATION=1 (and CSA_GW_CLIENT_SECRETS) to run live Google tests",
)


def _ws():
    secrets = os.environ.get("CSA_GW_CLIENT_SECRETS")
    if not secrets:
        pytest.skip("set CSA_GW_CLIENT_SECRETS to the OAuth client-secrets JSON path")
    from csa_google_workspace import Workspace
    return Workspace.from_oauth(secrets)


@contextlib.contextmanager
def _throwaway(ws, mime, name):
    """Create a throwaway Drive file of `mime`; always trash it on exit."""
    drive = ws._backend._services.drive
    fid = drive.files().create(body={"name": name, "mimeType": mime}, fields="id").execute()["id"]
    try:
        yield fid
    finally:
        drive.files().update(fileId=fid, body={"trashed": True}).execute()


def _assert_comment_lifecycle(doc):
    """The uniform comment lifecycle — must behave identically on every file type."""
    c = doc.create_comment("please review")
    assert c.resolved is False and c.content == "please review"
    c.reply("ack")
    c.resolve()
    assert doc.comments.get(c.id).resolved is True
    assert doc.comments.filter(resolved=False) == []
    c.reopen()
    assert doc.comments.get(c.id).resolved is False
    c.delete()
    assert doc.comments.all() == []                       # soft-deleted: hidden by default
    assert len(doc.comments.all(include_deleted=True)) == 1


def test_doc_end_to_end_live():
    from csa_google_workspace import Doc
    ws = _ws()
    with _throwaway(ws, "application/vnd.google-apps.document", "E2E-Doc-THROWAWAY") as fid:
        ws._backend._services.docs.documents().batchUpdate(
            documentId=fid,
            body={"requests": [{"insertText": {"location": {"index": 1},
                                               "text": "E2E doc line one.\n"}}]}).execute()
        d = ws.open(fid)
        assert isinstance(d, Doc) and d.type == "document"
        assert "E2E doc line one." in d.as_text()
        assert any("E2E doc line one." in p for p in d.paragraphs)
        assert d.export("application/pdf")[:4] == b"%PDF"
        _assert_comment_lifecycle(d)


def test_sheet_end_to_end_live():
    from csa_google_workspace import Sheet
    ws = _ws()
    with _throwaway(ws, "application/vnd.google-apps.spreadsheet", "E2E-Sheet-THROWAWAY") as fid:
        ws._backend._services.sheets.spreadsheets().values().update(
            spreadsheetId=fid, range="Sheet1!A1", valueInputOption="RAW",
            body={"values": [["Name", "Score"], ["Alice", "10"]]}).execute()
        s = ws.open(fid)
        assert isinstance(s, Sheet) and s.type == "spreadsheet"
        assert "Sheet1" in s.tabs
        assert s.values("Sheet1!A1:B2") == [["Name", "Score"], ["Alice", "10"]]
        assert "Name\tScore" in s.as_text()
        _assert_comment_lifecycle(s)


def test_slides_end_to_end_live():
    from csa_google_workspace import Slides
    ws = _ws()
    slides_api = ws._backend._services.slides
    with _throwaway(ws, "application/vnd.google-apps.presentation", "E2E-Slides-THROWAWAY") as fid:
        p = ws.open(fid)
        assert isinstance(p, Slides) and p.type == "presentation"
        assert len(p.slides) >= 1
        first = slides_api.presentations().get(presentationId=fid).execute()["slides"][0]["objectId"]
        slides_api.presentations().batchUpdate(presentationId=fid, body={"requests": [
            {"createShape": {"objectId": "e2etextbox1", "shapeType": "TEXT_BOX",
                "elementProperties": {"pageObjectId": first,
                    "size": {"width": {"magnitude": 300, "unit": "PT"},
                             "height": {"magnitude": 50, "unit": "PT"}},
                    "transform": {"scaleX": 1, "scaleY": 1,
                                  "translateX": 50, "translateY": 50, "unit": "PT"}}}},
            {"insertText": {"objectId": "e2etextbox1", "text": "E2E slide text"}}]}).execute()
        assert "E2E slide text" in ws.open(fid).as_text()
        _assert_comment_lifecycle(p)


def test_sheet_cell_mapping_live():
    from csa_google_workspace import Sheet
    ws = _ws()
    with _throwaway(ws, "application/vnd.google-apps.spreadsheet", "E2E-CellMap-THROWAWAY") as fid:
        ws._backend._services.sheets.spreadsheets().values().update(
            spreadsheetId=fid, range="A1", valueInputOption="RAW",
            body={"values": [["hdr"]]}).execute()
        s = ws.open(fid)
        assert isinstance(s, Sheet)
        c = s.create_comment("map me")           # API comment -> lands on A1 in the export
        loc = s.comments.get(c.id).location
        assert loc is not None and loc.cell == "A1", f"expected A1, got {loc}"
        c.delete()


def test_content_write_live():
    ws = _ws()
    with _throwaway(ws, "application/vnd.google-apps.document", "E2E-DocWrite-THROWAWAY") as fid:
        d = ws.open(fid)
        d.append_text("written by the library")
        assert "written by the library" in ws.open(fid).as_text()
        d.replace_text("written by the library", "edited by the library")
        assert "edited by the library" in ws.open(fid).as_text()
    with _throwaway(ws, "application/vnd.google-apps.spreadsheet", "E2E-SheetWrite-THROWAWAY") as sid:
        s = ws.open(sid)
        s.update("Sheet1!A1", [["hello", "world"]])
        assert s.values("Sheet1!A1:B1") == [["hello", "world"]]
        s.clear("Sheet1!A1:B1")
        assert s.values("Sheet1!A1:B1") == []


def test_suggestions_read_live():
    doc_id = os.environ.get("CSA_GW_SUGGESTIONS_DOC")
    if not doc_id:
        pytest.skip("set CSA_GW_SUGGESTIONS_DOC to a Doc id that has suggesting-mode edits")
    from csa_google_workspace import Doc
    ws = _ws()
    d = ws.open(doc_id)
    assert isinstance(d, Doc)
    sugg = d.suggestions
    assert isinstance(sugg, list) and all(s.kind in ("insertion", "deletion") for s in sugg)
    # accepted vs rejected previews should differ when suggestions exist
    if sugg:
        assert d.as_text(suggestions="accepted") != d.as_text(suggestions="rejected")

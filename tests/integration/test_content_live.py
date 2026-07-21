import os
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CSA_GW_INTEGRATION") != "1",
    reason="set CSA_GW_INTEGRATION=1 and CSA_GW_CLIENT_SECRETS to run live Google tests",
)


def test_doc_content_read_live():
    from csa_google_workspace import Workspace
    ws = Workspace.from_oauth(os.environ["CSA_GW_CLIENT_SECRETS"])
    drive = ws._backend._services.drive
    f = drive.files().create(
        body={"name": "PROBE-content-THROWAWAY",
              "mimeType": "application/vnd.google-apps.document"},
        fields="id").execute()
    fid = f["id"]
    try:
        # seed some text via the Docs API (write is not in the library yet, so use the raw client)
        ws._backend._services.docs.documents().batchUpdate(
            documentId=fid,
            body={"requests": [{"insertText": {"location": {"index": 1},
                                               "text": "Integration content line."}}]}).execute()
        doc = ws.open(fid)
        assert "Integration content line." in doc.as_text()
        assert any("Integration content line." in p for p in doc.paragraphs)
        assert doc.export("application/pdf")[:4] == b"%PDF"
    finally:
        drive.files().update(fileId=fid, body={"trashed": True}).execute()

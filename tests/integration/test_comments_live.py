import os
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CSA_GW_INTEGRATION") != "1",
    reason="set CSA_GW_INTEGRATION=1 and CSA_GW_CLIENT_SECRETS to run live Google tests",
)


def test_full_comment_lifecycle_live():
    from csa_google_workspace import Workspace
    from googleapiclient.discovery import build

    ws = Workspace.from_oauth(os.environ["CSA_GW_CLIENT_SECRETS"])
    drive = ws._backend._services.drive
    f = drive.files().create(
        body={"name": "PROBE-integration-THROWAWAY",
              "mimeType": "application/vnd.google-apps.document"},
        fields="id").execute()
    fid = f["id"]
    try:
        doc = ws.open(fid)
        c = doc.create_comment("integration comment")
        assert c.resolved is False and c.content == "integration comment"
        c.reply("a reply")
        c.resolve()
        assert doc.comments.get(c.id).resolved is True
        c.reopen()
        assert doc.comments.get(c.id).resolved is False
        c.delete()
        assert doc.comments.all() == []
        assert doc.comments.all(include_deleted=True)[0].deleted is True
    finally:
        drive.files().update(fileId=fid, body={"trashed": True}).execute()

import io, zipfile
from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend

SHEET = "application/vnd.google-apps.spreadsheet"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
NS = "http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments"
META = {"s": {"id": "s", "name": "S", "mimeType": SHEET, "webViewLink": "https://x/spreadsheets/d/s/edit"}}


def _xlsx(ref, author, text, dT):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/persons/person.xml",
                   f'<personList xmlns="{NS}"><person displayName="{author}" id="P1"/></personList>')
        z.writestr("xl/threadedComments/threadedComment1.xml",
                   f'<ThreadedComments xmlns="{NS}"><threadedComment ref="{ref}" dT="{dT}" '
                   f'personId="P1" id="G1"><text>{text}</text></threadedComment></ThreadedComments>')
    return buf.getvalue()


def _sheet_with_mapped_comment():
    b = FakeBackend(META)
    c = b.create_comment("s", "check West")        # FakeBackend sets author "Test User", createdTime 2026-01-01T00:00:00Z
    b._exports[("s", XLSX)] = _xlsx("B11", "Test User", "check West", "2026-01-01T00:00:00.00")
    return Workspace(b).open("s"), c["id"]


def test_comment_location_populated():
    sheet, cid = _sheet_with_mapped_comment()
    assert sheet.comments.get(cid).location.cell == "B11"


def test_comments_by_cell():
    sheet, cid = _sheet_with_mapped_comment()
    hits = sheet.comments_by_cell("B11")
    assert [c.id for c in hits] == [cid]
    assert sheet.comments_by_cell("Z99") == []


def test_location_none_when_no_export_match():
    b = FakeBackend(META)
    c = b.create_comment("s", "unmapped")
    b._exports[("s", XLSX)] = _xlsx("B11", "Someone Else", "different", "2026-01-01T00:00:00.00")
    sheet = Workspace(b).open("s")
    assert sheet.comments.get(c["id"]).location is None

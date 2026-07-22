import pytest

from csa_google_workspace import Doc, Sheet, Slides, Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.workspace import parse_file_id

DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"
SLIDES = "application/vnd.google-apps.presentation"
FILES = {
    "d1": {"id": "d1", "name": "Doc", "mimeType": DOC, "webViewLink": "https://x/document/d/d1/edit"},
    "s1": {"id": "s1", "name": "Sheet", "mimeType": SHEET, "webViewLink": "https://x/spreadsheets/d/s1/edit"},
    "p1": {"id": "p1", "name": "Deck", "mimeType": SLIDES, "webViewLink": "https://x/presentation/d/p1/edit"},
}


@pytest.mark.parametrize("value,expected", [
    ("d1", "d1"),
    ("https://docs.google.com/document/d/ABC123/edit?tab=t.0", "ABC123"),
    ("https://docs.google.com/spreadsheets/d/S-9_x/edit#gid=0", "S-9_x"),
    ("https://drive.google.com/file/d/FID/view", "FID"),
])
def test_parse_file_id(value, expected):
    assert parse_file_id(value) == expected


def test_open_returns_typed_subclass():
    ws = Workspace(FakeBackend(FILES))
    assert isinstance(ws.open("d1"), Doc)
    assert isinstance(ws.open("s1"), Sheet)
    assert isinstance(ws.open("p1"), Slides)


def test_open_by_url_extracts_id_then_opens():
    ws = Workspace(FakeBackend(FILES))
    with pytest.warns(DeprecationWarning):
        d = ws.open_by_url("https://docs.google.com/document/d/d1/edit")
    assert isinstance(d, Doc) and d.id == "d1"


def test_read_only_propagates_to_document():
    ws = Workspace(FakeBackend(FILES), read_only=True)
    assert ws.open("d1").read_only is True


def test_from_credentials_wires_apibackend_and_propagates_read_only():
    from csa_google_workspace.backend import ApiBackend
    ws = Workspace.from_credentials("sentinel-creds", read_only=True)
    assert ws.read_only is True
    assert isinstance(ws._backend, ApiBackend)


def test_from_credentials_defaults_to_read_write():
    ws = Workspace.from_credentials("sentinel-creds")
    assert ws.read_only is False

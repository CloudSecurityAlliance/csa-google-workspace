from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend

SHEET = "application/vnd.google-apps.spreadsheet"
META = {"s": {"id": "s", "name": "S", "mimeType": SHEET, "webViewLink": "https://x/spreadsheets/d/s/edit"}}


def sheet():
    return Workspace(FakeBackend(
        META,
        spreadsheets={"s": {"sheets": [{"properties": {"sheetId": 0, "title": "Sheet1"}},
                                        {"properties": {"sheetId": 1, "title": "Data"}}]}},
        values={("s", "Sheet1"): [["h1", "h2"], ["1", "2"]]},
    )).open("s")


def test_tabs_lists_titles():
    assert sheet().tabs == ["Sheet1", "Data"]


def test_values_returns_grid():
    assert sheet().values("Sheet1") == [["h1", "h2"], ["1", "2"]]


def test_as_text_joins_rows_and_cells():
    t = sheet().as_text()
    assert "h1\th2" in t and "1\t2" in t

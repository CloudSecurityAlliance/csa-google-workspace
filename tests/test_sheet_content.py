import pytest

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


def _multi_tab_sheet():
    return Workspace(FakeBackend(
        META,
        spreadsheets={"s": {"sheets": [{"properties": {"sheetId": 0, "title": "Sheet1"}},
                                        {"properties": {"sheetId": 1, "title": "Data"}}]}},
        values={("s", "Sheet1"): [["a1"]], ("s", "Data"): [["d1"]]},
    )).open("s")


def test_as_text_renders_all_tabs_with_headers_by_default():
    t = _multi_tab_sheet().as_text()
    assert "# Sheet1" in t and "a1" in t          # first tab
    assert "# Data" in t and "d1" in t            # second tab no longer silently dropped


def test_as_text_named_tab_renders_only_that_tab_without_header():
    t = _multi_tab_sheet().as_text(tab="Data")
    assert t == "d1"


def test_as_text_unknown_tab_raises_valueerror():
    with pytest.raises(ValueError):
        _multi_tab_sheet().as_text(tab="Nope")


def test_as_text_single_tab_has_no_header():
    s = Workspace(FakeBackend(
        META,
        spreadsheets={"s": {"sheets": [{"properties": {"sheetId": 0, "title": "Only"}}]}},
        values={("s", "Only"): [["x", "y"]]},
    )).open("s")
    assert s.as_text() == "x\ty"                  # unchanged single-tab behaviour

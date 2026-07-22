"""Tab-name quoting for A1 ranges (audit finding #2).

A tab name may go unquoted in an A1 range only if it reads as a plain identifier
and is not itself a cell reference. Numeric ("2024"), leading-digit, non-ASCII, and
space-containing names must be single-quoted, or Sheets rejects the range with a 400.
"""
import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend

SHEET = "application/vnd.google-apps.spreadsheet"
META = {"s": {"id": "s", "name": "S", "mimeType": SHEET, "webViewLink": "https://x/spreadsheets/d/s/edit"}}


def _sheet_with_tab(title):
    return Workspace(FakeBackend(
        META,
        spreadsheets={"s": {"sheets": [{"properties": {"sheetId": 0, "title": title}}]}},
    )).open("s")


@pytest.mark.parametrize("title, expected", [
    ("2024", "'2024'"),               # all-digit (year tabs) — the reported bug
    ("1stQuarter", "'1stQuarter'"),   # leading digit
    ("café", "'café'"),               # non-ASCII
    ("Q1 2024", "'Q1 2024'"),         # spaces
    ("A1", "'A1'"),                   # cell-reference-like — must stay quoted
    ("O'Brien", "'O''Brien'"),        # embedded single quote is doubled
    ("Sheet1", "Sheet1"),             # plain identifier — stays unquoted
    ("Data", "Data"),                 # plain identifier — stays unquoted
    ("Tab_2", "Tab_2"),               # identifier with underscore/digit — unquoted
])
def test_quote_tab(title, expected):
    assert _sheet_with_tab(title)._quote_tab(title) == expected


def test_as_text_uses_quoted_range_for_numeric_tab():
    # Values are stored under the QUOTED range. If as_text() queries the bare
    # "2024" (the bug) it misses them and renders empty.
    ws = Workspace(FakeBackend(
        META,
        spreadsheets={"s": {"sheets": [{"properties": {"sheetId": 0, "title": "2024"}}]}},
        values={("s", "'2024'"): [["revenue", "100"]]},
    ))
    assert ws.open("s").as_text() == "revenue\t100"

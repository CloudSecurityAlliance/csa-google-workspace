import pytest
from csa_google_workspace import Workspace, exceptions as exc
from csa_google_workspace.backend import FakeBackend

SHEET = "application/vnd.google-apps.spreadsheet"
META = {"s": {"id": "s", "name": "S", "mimeType": SHEET, "webViewLink": "https://x/spreadsheets/d/s/edit"}}


def sheet(read_only=False):
    b = FakeBackend(META)
    return Workspace(b, read_only=read_only).open("s"), b


def test_update_writes_values_and_reads_back():
    s, b = sheet()
    s.update("Sheet1!A1", [["a", "b"]])
    assert ("s", "sheets_values_update", "Sheet1!A1", [["a", "b"]], "RAW") in b._writes
    assert s.values("Sheet1!A1") == [["a", "b"]]


def test_update_passes_value_input_option():
    s, b = sheet()
    s.update("Sheet1!A1", [["=SUM(B:B)"]], value_input_option="USER_ENTERED")
    assert ("s", "sheets_values_update", "Sheet1!A1", [["=SUM(B:B)"]], "USER_ENTERED") in b._writes


def test_clear_records():
    s, b = sheet()
    s.update("Sheet1!A1", [["x"]]); s.clear("Sheet1!A1")
    assert ("s", "sheets_values_clear", "Sheet1!A1") in b._writes
    assert s.values("Sheet1!A1") == []


def test_batch_update_records():
    s, b = sheet()
    s.batch_update([{"repeatCell": {}}])
    assert ("s", "sheets", [{"repeatCell": {}}]) in b._writes


def test_writes_blocked_when_read_only():
    s, _ = sheet(read_only=True)
    for call in (lambda: s.update("A1", [["x"]]), lambda: s.clear("A1"), lambda: s.batch_update([{}])):
        with pytest.raises(exc.ReadOnlyError):
            call()

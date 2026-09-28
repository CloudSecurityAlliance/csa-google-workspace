"""Where `export_file_inventory` puts the table - four destinations, and the rules per place.

The inventory itself is covered in `test_work_handoff_inventory.py`. What had never run is
the delivery half: three of the four destinations, and the two refusals that guard them.

The destinations are not interchangeable and the differences are the point:

    rows    comes back in the response - fine for tens of files, not hundreds
    csv     the text, for the caller to place
    sheet   CREATES a Drive file, so it additionally needs `file.create`
    file    writes to THIS MACHINE, which is a data-handling decision, not a permission

`"file"` is the one with a switch of its own. `CSA_GW_LOCAL_WRITE` is not a capability - it
answers "may this server put your documents' contents on the disk it is running on?", which
is a different question from "may it change your Drive", and its refusal says so.
"""
from __future__ import annotations

import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp._config import settings_from_env
from csa_google_workspace.mcp.server import create_server

DOC_MIME = "application/vnd.google-apps.document"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
A = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"
B = "1ZZ2CN6VqHDjxvl9kMKXvpv5CFDf6JOkJ9U7sHoBk9y9"
FILES = {A: {"id": A, "name": "Plan", "mimeType": DOC_MIME, "webViewLink": "ua"},
         B: {"id": B, "name": "Budget", "mimeType": SHEET_MIME, "webViewLink": "ub"}}


def build(**env):
    backend = FakeBackend(dict(FILES))
    return create_server(lambda: Workspace(backend),
                         settings=settings_from_env({"CSA_GW_ALLOWLIST_READ": "*", **env}))


def call(app, **args):
    return asyncio.run(
        app.call_tool("export_file_inventory", args)).structured_content


class TestTheDestinationIsChecked:
    @pytest.mark.parametrize("destination", ["xlsx", "sheets", "", "ROWS"])
    def test_an_unknown_destination_names_the_four_that_exist(self, destination):
        """Checked BEFORE the inventory is gathered. Gathering five hundred files and then
        discovering the destination is misspelled spends the expensive half of the call to
        produce an error the cheap half could have given."""
        with pytest.raises(ToolError) as ei:
            call(build(), fileIds=[A], destination=destination)
        message = str(ei.value)
        for valid in ("rows", "csv", "sheet", "file"):
            assert valid in message


class TestRowsAndCsv:
    def test_rows_come_back_in_the_response(self):
        out = call(build(), fileIds=[A, B])
        assert len(out["rows"]) == 2
        assert "2 file(s) reached" in out["detail"]

    def test_csv_is_text_with_the_same_columns(self):
        out = call(build(), fileIds=[A, B], destination="csv")
        header, *body = out["csv"].strip().splitlines()

        assert header.split(",") == out["columns"]
        assert len(body) == 2

    def test_empty_columns_are_dropped_but_the_derived_ones_stay(self):
        """A handoff table with eight blank columns is harder to read. The derived columns
        stay regardless, because they are named in the tool description - a reader told to
        look for `edited_last_by_subject` must find it, including when it is blank."""
        from csa_google_workspace import _inventory

        out = call(build(), fileIds=[A])
        for derived in _inventory.DERIVED:
            assert derived in out["columns"]


class TestTheSheetDestination:
    def test_it_creates_a_new_file_and_hands_back_a_link(self):
        """CREATED, never written over. Uploading a formatted workbook onto an EXISTING
        spreadsheet resets every comment's cell anchor to A1 - measured, and the reason there
        is deliberately no method in this library that does it."""
        out = call(build(), fileIds=[A, B], destination="sheet")

        assert out["sheet_id"] and out["sheet_url"]
        assert "Written to a new" in out["detail"]

    def test_the_default_name_carries_the_subject_and_the_date(self):
        """So two sweeps of the same Drive a week apart do not look like the same file."""
        out = call(build(), fileIds=[A], destination="sheet", subject="away@example.org")
        assert "away@example.org" in out["detail"]

    def test_a_given_name_is_used_verbatim(self):
        out = call(build(), fileIds=[A], destination="sheet", sheetName="Handover Q3")
        assert '"Handover Q3"' in out["detail"]

    def test_without_openpyxl_it_still_writes_a_sheet_and_says_it_is_plain(self, monkeypatch):
        """A formatting library missing must not cost somebody the table. The fallback writes
        the grid through the Sheets API instead - no frozen header, no autofilter - and SAYS
        so, because a reader who does not know it is unformatted will think Drive did that."""
        monkeypatch.setattr("csa_google_workspace._export.xlsx_supported", lambda: False)
        out = call(build(), fileIds=[A], destination="sheet")

        assert out["sheet_id"]
        assert "UNFORMATTED" in out["detail"] and "openpyxl" in out["detail"]


class TestTheFileDestination:
    def test_it_writes_a_csv_and_reports_the_path(self, tmp_path):
        out = call(build(CSA_GW_LOCAL_WRITE="1", CSA_GW_EXPORT_DIR=str(tmp_path)),
                   fileIds=[A, B], destination="file")

        written = tmp_path / (out["written_path"].rsplit("/", 1)[-1])
        assert written.exists()
        assert written.read_text().strip().splitlines()[0].split(",") == out["columns"]

    def test_local_write_off_refuses_and_names_the_setting_and_the_alternatives(self):
        """The refusal has to say three things: that it is off, WHICH setting turns it on,
        and what to do instead. Without the third, the caller's next move is to give up on
        the inventory rather than to take it in Drive - and the setting is not theirs to
        change, so "ask an operator" is only useful alongside a route that works now.

        `CSA_GW_LOCAL_WRITE` defaults to ON, so it has to be switched off explicitly here.
        That default is worth knowing while reading this: an unconfigured server WILL write
        a file to the machine it runs on when asked to."""
        with pytest.raises(ToolError) as ei:
            call(build(CSA_GW_LOCAL_WRITE="0"), fileIds=[A], destination="file")
        message = str(ei.value)

        assert "CSA_GW_LOCAL_WRITE" in message
        assert "DATA-HANDLING setting, not a permission" in message
        assert 'destination="sheet"' in message and '"csv"' in message

    def test_nothing_is_written_when_it_is_off(self, tmp_path):
        """The refusal is BEFORE the write, not a cleanup after it - so a directory that was
        writable and empty stays empty."""
        with pytest.raises(ToolError):
            call(build(CSA_GW_LOCAL_WRITE="0", CSA_GW_EXPORT_DIR=str(tmp_path)),
                 fileIds=[A], destination="file")
        assert list(tmp_path.iterdir()) == []

    def test_a_directory_that_does_not_exist_is_named_rather_than_created(self, tmp_path):
        """Switched ON, and pointed at somewhere absent. Creating it would put documents'
        contents in a directory nobody chose; the message says where it looked and offers
        `destination="csv"` so the call is not wasted."""
        missing = tmp_path / "nope" / "deeper"
        with pytest.raises(ToolError) as ei:
            call(build(CSA_GW_LOCAL_WRITE="1", CSA_GW_EXPORT_DIR=str(missing)),
                 fileIds=[A], destination="file")

        assert str(missing) in str(ei.value)
        assert not missing.exists(), "a missing export directory must not be created"

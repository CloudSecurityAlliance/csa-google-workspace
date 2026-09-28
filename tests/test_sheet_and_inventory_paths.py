"""Tab operations on a spreadsheet, and two blanks in the inventory that mean different things.

The tab refusals share a shape worth naming: both are case-insensitive, because Google's own
tab names are. `add_tab("register")` against an existing `Register` is a CLASH, not a new tab,
and a library that compared exactly would ask Google to create one and get "Register 2" back.

The inventory blanks are the other half of the same discipline. `owner` blank because the file
has no owner Drive would name, and `comments_by_subject` blank because comments were not
gathered, are different facts, and a register that renders both as empty cells says neither.
"""
from __future__ import annotations

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace import exceptions as exc
from csa_google_workspace.backend import FakeBackend

SHEET_MIME = "application/vnd.google-apps.spreadsheet"
SHEET = "s1"


def sheet(tabs=("Sheet1",), values=None):
    backend = FakeBackend(
        {SHEET: {"id": SHEET, "name": "Book", "mimeType": SHEET_MIME}},
        spreadsheets={SHEET: {"sheets": [{"properties": {"title": t, "sheetId": i}}
                                         for i, t in enumerate(tabs)]}},
        values=values or {})
    return Workspace(backend).open(SHEET)


class TestAddingATabThatIsAlreadyThere:
    def test_an_exact_clash_names_the_tab_and_creates_nothing(self):
        with pytest.raises(exc.ConflictError) as ei:
            sheet(("Sheet1", "Register")).add_tab("Register")

        message = str(ei.value)
        assert "'Register' already exists" in message
        assert "Nothing was created" in message

    def test_a_clash_differing_only_in_case_is_still_a_clash(self):
        """Google's tab names are case-insensitive. Comparing exactly would send the request,
        and Drive would answer with a SECOND tab called "register 2" - a silent duplicate that
        a register build finds weeks later."""
        with pytest.raises(exc.ConflictError) as ei:
            sheet(("Sheet1", "Register")).add_tab("register")

        message = str(ei.value)
        assert "'Register'" in message, "the refusal must name the tab that EXISTS"
        assert "you asked for 'register'" in message, "and the one that was asked for"

    def test_a_name_that_does_not_clash_is_created(self):
        assert sheet(("Sheet1",)).add_tab("Register")["title"] == "Register"


class TestDeletingATabByName:
    def test_an_unknown_name_lists_the_ones_that_exist(self):
        """A tab name is typed from memory more often than any id in this library. Listing
        the real ones turns a refusal into the answer."""
        with pytest.raises(exc.NotFoundError) as ei:
            sheet(("Sheet1", "Data")).delete_tab("Registr")

        message = str(ei.value)
        assert "'Registr'" in message
        assert "Sheet1" in message and "Data" in message

    def test_a_name_differing_only_in_case_still_finds_it(self):
        """The mirror of the add: case-insensitive both ways, or one of them is wrong."""
        book = sheet(("Sheet1", "Data"))
        book.delete_tab("data")
        assert "Data" not in book.tabs


class TestReadingASheetWithNoMetadata:
    def test_it_falls_back_to_a_default_range_rather_than_returning_nothing(self):
        """A spreadsheet whose `sheets` array came back empty - a permission shape, or a
        response this library did not expect. Returning "" would report an empty spreadsheet,
        which is a claim about somebody's data rather than about the response."""
        backend = FakeBackend({SHEET: {"id": SHEET, "name": "Book", "mimeType": SHEET_MIME}},
                              spreadsheets={SHEET: {}},
                              values={(SHEET, "A1:Z1000"): [["a", "b"]]})
        text = Workspace(backend).open(SHEET).as_text()

        assert "a" in text and "b" in text

    def test_an_unknown_tab_is_refused_with_the_list_of_real_ones(self):
        with pytest.raises(ValueError) as ei:
            sheet(("Sheet1", "Data")).as_text(tab="Nope")
        assert "Sheet1" in str(ei.value) and "Data" in str(ei.value)


class TestNamingAProtectedRange:
    def test_a_protection_with_no_keys_at_all_is_not_reported_as_one_cell(self):
        """The commonest protection there is: the whole sheet, expressed as a grid range with
        no row or column indices. Rendering it `A1:A1` would report a whole-sheet lock as a
        single cell, which is the difference between "you cannot edit this" and "you cannot
        edit one cell"."""
        from csa_google_workspace.documents.sheet import _grid_to_a1

        assert _grid_to_a1({}, "Sheet1") != "Sheet1!A1:A1"

    def test_nothing_at_all_is_none(self):
        from csa_google_workspace.documents.sheet import _grid_to_a1

        assert _grid_to_a1({}, None) is None


class TestTwoBlanksThatMeanDifferentThings:
    def test_no_actors_gives_two_blanks_rather_than_a_pair_of_empty_strings_in_a_list(self):
        """Drive omits owner information on some files - a shared drive item, a file whose
        owner's account is gone. Two blanks, not `"; "`, which is what joining an empty list
        of names with a separator would have produced on a register somebody reads."""
        from csa_google_workspace import _inventory

        assert _inventory._actor_names([]) == ("", "")

    def test_actors_are_joined_and_the_two_columns_stay_aligned(self):
        """Names and addresses are separate columns and the same ORDER, so a reader can pair
        them off by position. A name with no address contributes an empty slot rather than
        shortening the second column and shifting everybody after it."""
        from csa_google_workspace import _inventory
        from csa_google_workspace.files import FileActor

        names, emails = _inventory._actor_names([
            FileActor(display_name="A Person", email="a@example.org", me=False),
            FileActor(display_name="No Address", email=None, me=False),
        ])

        assert names == "A Person; No Address"
        assert emails == "a@example.org; "
        assert names.count(";") == emails.count(";"), "the columns no longer line up"

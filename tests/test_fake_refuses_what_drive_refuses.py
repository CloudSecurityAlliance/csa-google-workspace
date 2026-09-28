"""`FakeBackend` declining the things Google declines.

A test double that is more permissive than the system it stands for does not merely fail to
catch a bug - it CERTIFIES the bug. This repo has the scar: the fake returned deleted comments
happily, so `delete_comment` re-fetching what it had just deleted passed every unit test and
failed against real Google with "Comment not found". The fix was to make the fake refuse it.

These are the remaining refusals on that list. None of them is about the library's behaviour;
each is about whether the double can be trusted to disprove something.
"""
from __future__ import annotations

import pytest

from csa_google_workspace import exceptions as exc
from csa_google_workspace.backend import FakeBackend

DOC_MIME = "application/vnd.google-apps.document"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"


def sheet_backend(tabs=("Sheet1",)):
    return FakeBackend(
        {"s1": {"id": "s1", "name": "Book", "mimeType": SHEET_MIME}},
        spreadsheets={"s1": {"sheets": [{"properties": {"title": t, "sheetId": i}}
                                        for i, t in enumerate(tabs)]}})


def doc_backend(tab_count=1):
    tabs = [{"tabProperties": {"title": f"Tab {i + 1}", "tabId": f"t.{i}", "index": i},
             "documentTab": {"body": {"content": []}}} for i in range(tab_count)]
    return FakeBackend({"d1": {"id": "d1", "name": "Draft", "mimeType": DOC_MIME}},
                       documents={"d1": {"tabs": tabs}})


class TestTheLastTabCannotBeRemoved:
    """Google requires a spreadsheet to keep at least one sheet, and a document at least one
    tab. A fake that allowed it would let a cleanup routine be written that empties a file and
    passes, then fails in front of somebody's real document."""

    def test_a_spreadsheet_keeps_its_only_sheet(self):
        with pytest.raises(exc.ConflictError, match="at least one"):
            sheet_backend().sheets_delete_tab("s1", 0)

    def test_with_two_sheets_one_can_go(self):
        """The refusal has to be about the LAST one, not about deleting at all."""
        backend = sheet_backend(("Sheet1", "Sheet2"))
        backend.sheets_delete_tab("s1", 1)
        assert len(backend.get_spreadsheet("s1")["sheets"]) == 1

    def test_a_document_keeps_its_only_tab(self):
        with pytest.raises(exc.ConflictError, match="at least one"):
            doc_backend(tab_count=1).docs_delete_tab("d1", "t.0")

    def test_with_two_tabs_one_can_go(self):
        backend = doc_backend(tab_count=2)
        backend.docs_delete_tab("d1", "t.0")
        assert len(backend.get_document("d1")["tabs"]) == 1


class TestNamingSomethingThatIsNotThere:
    def test_an_unknown_sheet_id_is_not_found(self):
        with pytest.raises(exc.NotFoundError, match="sheetId"):
            sheet_backend(("Sheet1", "Sheet2")).sheets_delete_tab("s1", 99)

    def test_an_unknown_tab_id_is_not_found(self):
        with pytest.raises(exc.NotFoundError, match="t.missing"):
            doc_backend(tab_count=2).docs_delete_tab("d1", "t.missing")

    def test_an_unknown_label_definition_is_not_found(self):
        """`list_file_labels` gives ids; the definitions give them NAMES. A fake that invented
        an empty definition would let a display path be written that renders every label as
        blank and never notices."""
        with pytest.raises(exc.NotFoundError, match="label definition"):
            FakeBackend({}).get_label_definition("labels/unknown")

    def test_a_file_with_no_uploaded_bytes_cannot_be_downloaded(self):
        """`download_file` returns what was UPLOADED. A Google-native file has no such bytes -
        it has exports - and returning b"" for one would make an empty download look like an
        empty document."""
        with pytest.raises(exc.NotFoundError, match="no uploaded bytes"):
            FakeBackend({"f": {"id": "f", "name": "D", "mimeType": DOC_MIME}}).download_file("f")


class TestADuplicateTabNameIsLoudRatherThanSilent:
    def test_adding_a_tab_that_already_exists_conflicts(self):
        """Google would name it "Register 2" and carry on. A caller re-running a register
        build needs "already there" told apart from "created", and a silent rename gives them
        a second tab they will find weeks later."""
        with pytest.raises(exc.ConflictError, match="already exists"):
            sheet_backend(("Sheet1", "Register")).sheets_add_tab("s1", "Register")

    def test_a_new_name_is_created(self):
        backend = sheet_backend()
        props = backend.sheets_add_tab("s1", "Register")
        assert props["title"] == "Register"


class TestALegacyFixtureIsPromotedIntoTheTabsShape:
    def test_a_body_only_document_grows_a_first_tab_when_a_second_is_added(self):
        """Google returns a single-tab document as a bare `body` and a multi-tab one as
        `tabs`. A fixture written in the old shape must become the new one on the first add,
        or the fake models a document Google cannot produce: two tabs and a stray body."""
        backend = FakeBackend({"d1": {"id": "d1", "name": "Draft", "mimeType": DOC_MIME}},
                              documents={"d1": {"body": {"content": ["original"]}}})
        backend.docs_add_tab("d1", "Second")
        tabs = backend.get_document("d1")["tabs"]

        assert len(tabs) == 2, "the original body was not promoted into a tab"
        assert tabs[0]["documentTab"]["body"]["content"] == ["original"]
        assert tabs[1]["tabProperties"]["title"] == "Second"

    def test_an_empty_document_starts_with_the_tab_that_was_added(self):
        """Nothing to promote. The new tab is the first one, not the second."""
        backend = FakeBackend({"d1": {"id": "d1", "name": "Draft", "mimeType": DOC_MIME}},
                              documents={"d1": {}})
        backend.docs_add_tab("d1", "First")

        assert len(backend.get_document("d1")["tabs"]) == 1


class TestALinkShareHasNoAddress:
    def test_an_anyone_permission_carries_no_email(self):
        """The fake mirrors what Drive stores. A permission with an address on it would make
        `get_file_permissions` report a link share as a grant to a named person - which is the
        opposite of the thing somebody is checking for when they ask who can see a file."""
        backend = FakeBackend({"f": {"id": "f", "name": "D", "mimeType": DOC_MIME}})
        perm = backend.create_permission("f", email=None, role="reader",
                                         permission_type="anyone")

        assert perm["type"] == "anyone" and perm["role"] == "reader"
        assert "emailAddress" not in perm

    def test_a_named_grant_keeps_its_address(self):
        backend = FakeBackend({"f": {"id": "f", "name": "D", "mimeType": DOC_MIME}})
        perm = backend.create_permission("f", email="a@b.c", role="writer")
        assert perm["emailAddress"] == "a@b.c"

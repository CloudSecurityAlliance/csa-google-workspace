"""The last branches, and what each of them is the absence of.

Almost every one is a case where something is MISSING - a `name` attribute on a sheet element,
a relationship id that matches nothing, a `childTabs` list, an `as_text` method, a policy. The
shared discipline is that an absence produces a usable answer rather than an exception, because
all of this runs inside a call somebody is waiting on and a partial answer beats none.

The two exceptions to that are the ones that fail closed, and they are marked as such: a
file-scoped call with no file id, and an allowlist entry whose id cannot be extracted. Both
say "this is a bug" in the message, because the right fix is upstream rather than a wider
policy.
"""
from __future__ import annotations

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend

DOC_MIME = "application/vnd.google-apps.document"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
FOLDER_MIME = "application/vnd.google-apps.folder"


class TestReferencesThisParserCannotPlace:
    """`.xlsx` parsing, where a cell reference may be a shape this library does not model -
    a defined name, a cross-sheet reference. It runs inside an export somebody is waiting on,
    so an unrecognised ref produces a usable row rather than an exception."""

    def test_a_reference_with_no_tab_does_not_get_one_invented(self):
        from csa_google_workspace import _cellmap

        assert _cellmap.location_from_ref("B2", None).tab is None

class TestTabsInsideTabs:
    def test_a_child_tab_is_listed_with_its_nesting_level(self):
        """Google Docs tabs nest. A flat walk would list only the top level, and a register
        naming "Appendix" would point at a tab the reader cannot find because it is inside
        another one."""
        raw = {"tabs": [{
            "tabProperties": {"title": "Main", "tabId": "t.0", "index": 0},
            "childTabs": [{"tabProperties": {"title": "Appendix", "tabId": "t.1", "index": 0}}],
        }]}
        backend = FakeBackend({"d1": {"id": "d1", "name": "Draft", "mimeType": DOC_MIME}},
                              documents={"d1": raw})
        tabs = Workspace(backend).open("d1").document_tabs

        assert [t["title"] for t in tabs] == ["Main", "Appendix"]
        assert [t["nesting_level"] for t in tabs] == [0, 1]

    def test_googles_own_nesting_level_wins_over_the_computed_one(self):
        """`depth` is the FALLBACK. If Google says otherwise, Google is describing its own
        document and this is describing a traversal."""
        raw = {"tabs": [{
            "tabProperties": {"title": "Main", "tabId": "t.0", "index": 0},
            "childTabs": [{"tabProperties": {"title": "Deep", "tabId": "t.1", "index": 0,
                                             "nestingLevel": 4}}],
        }]}
        backend = FakeBackend({"d1": {"id": "d1", "name": "Draft", "mimeType": DOC_MIME}},
                              documents={"d1": raw})
        assert Workspace(backend).open("d1").document_tabs[1]["nesting_level"] == 4


class TestASheetIdThatIsNotThere:
    def test_an_unknown_tab_title_falls_back_to_the_first_sheet(self):
        """`_gid` answers "which sheetId" for an operation already validated elsewhere. Zero
        is the first sheet, which is Google's own default for a range with no sheet - a usable
        answer rather than an exception inside a call that has already been permitted."""
        from csa_google_workspace.documents.sheet import Sheet

        backend = FakeBackend(
            {"s1": {"id": "s1", "name": "Book", "mimeType": SHEET_MIME}},
            spreadsheets={"s1": {"sheets": [{"properties": {"title": "Sheet1",
                                                            "sheetId": 7}}]}})
        book: Sheet = Workspace(backend).open("s1")

        assert book._gid("Sheet1") == 7
        assert book._gid("NoSuchTab") == 0


class TestCountingAMatchByNameAlone:
    def test_a_display_name_basis_is_counted_as_a_weaker_match(self):
        """Matching a person by DISPLAY NAME is not matching them by address: names are
        neither unique nor stable, and a sweep that attributes a file on a name alone can
        attribute somebody else's work. The count exists so the caveat can say how much of the
        table rests on it."""
        from csa_google_workspace import _inventory
        from csa_google_workspace.files import FileActor

        assert _inventory._matches(
            FileActor(display_name="Away Person", email=None, me=False),
            "Away Person") == "display_name"
        assert _inventory._matches(
            FileActor(display_name="Away Person", email="away@example.org", me=False),
            "away@example.org") == "email"


class TestReadingAFileTypeWithNoText:
    def test_a_folder_says_what_to_do_instead(self):
        """"It has no text" is true and useless. The reply names the call that DOES list what
        is inside, because that is what somebody asking to read a folder wanted."""
        from csa_google_workspace.mcp._tools.content import _cannot_read

        message = _cannot_read("Archive", FOLDER_MIME)
        assert "is a folder" in message
        assert "search_files" in message and "in parents" in message

    def test_another_unreadable_type_gets_the_general_answer(self):
        from csa_google_workspace.mcp._tools.content import _cannot_read

        assert "Archive" in _cannot_read("Archive", "application/zip")


class TestAnAllowlistThatCannotBeUsed:
    @pytest.mark.parametrize("text, phrase", [
        pytest.param("https:///d/abc", "not a Google document URL", id="scheme-no-host"),
        pytest.param("not a url at all", "bare file id", id="bare-id"),
        pytest.param("https://docs.google.com/document/edit", "'/d/<id>' segment",
                     id="google-but-no-id"),
    ])
    def test_each_malformed_entry_is_diagnosed_by_shape(self, text, phrase):
        """The diagnosis is the whole value. "Invalid entry" sends somebody to re-read the
        documentation; "copy the whole address from your browser while the document is open"
        is the fix."""
        from csa_google_workspace.allowlist import diagnose_url

        assert phrase in diagnose_url(text)

    def test_a_variable_set_but_empty_is_not_the_same_as_unset(self):
        """A config template or an unexpanded shell variable. Unset means "everything";
        set-but-empty means "nothing", and a server that started with the first when the
        operator wrote the second is open when they believe it is closed - so the message
        names the likely cause rather than only the symptom."""
        from csa_google_workspace.allowlist import diagnose_setting

        message = diagnose_setting("CSA_GW_ALLOWLIST_MODIFY", "")
        assert "set but empty" in message and "not the same as unset" in message
        assert "config template" in message or "shell variable" in message

    def test_a_variable_whose_entries_are_all_comments_says_so_differently(self):
        from csa_google_workspace.allowlist import diagnose_setting

        assert "no usable entries" in diagnose_setting("CSA_GW_ALLOWLIST_MODIFY", "# just a note")


class TestPreviewingTheAllowlist:
    def test_a_repeated_file_id_is_resolved_once(self):
        """A list naming the same document twice - two lines, two reasons - must not cost two
        Drive calls. The preview is run at startup on a list that can be hundreds long."""
        from csa_google_workspace.allowlist import Entry, Listing, preview

        calls = []

        def fetch(file_id):
            calls.append(file_id)
            return {"id": file_id, "name": "A Doc", "mimeType": DOC_MIME}

        entry = Entry(file_id="abc", url="u", reason="first", line=1)
        again = Entry(file_id="abc", url="u", reason="second", line=2)
        result = preview(Listing(all_files=False, entries=(entry, again)), fetch)

        assert len(result.entries) == 2, "both lines are still reported"
        assert calls == ["abc"], "the same id was fetched twice"

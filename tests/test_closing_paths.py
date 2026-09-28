"""The last branches: bounded parsing, a retired variable, and two fail-closed refusals.

Three things worth reading for, rather than a list of modules:

**A parser with a budget.** `.xlsx` is a zip and a caller-supplied one may be a bomb, so every
member read is bounded by size, by total, and by count. What matters is the POSTURE when a
bound is hit: the mapping degrades - a comment loses its tab - and the export still happens.
Refusing the file would trade the valuable half for the decorative one.

**A variable that was split.** `CSA_GW_ALLOWLIST` became two, because reads and mutations want
different answers. Silently treating an old one as the modify list would leave `read`
fail-closed and break reads for reasons nobody could see.

**Two refusals that say "this is a bug".** A file-scoped call with no file id, and an allowlist
entry that passed validation and yielded no id. Neither is a configuration problem, and saying
so is what stops somebody widening a policy to work around a defect.
"""
from __future__ import annotations

import io
import zipfile

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace import exceptions as exc
from csa_google_workspace.backend import FakeBackend

DOC_MIME = "application/vnd.google-apps.document"


class TestTheXlsxParserDegradesRatherThanRefuses:
    @staticmethod
    def book(members):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, body in members.items():
                archive.writestr(name, body)
        return buffer.getvalue()

    def test_malformed_xml_in_the_relationship_graph_costs_the_tab_not_the_export(self, caplog):
        """A damaged or truncated part. The cell reference and the comment text are still
        there; only the sheet NAME is lost - which is the decorative half."""
        from csa_google_workspace._cellmap import parse_xlsx_comments

        data = self.book({
            "xl/workbook.xml": b"<not valid xml",
            "_rels/.rels": b"<Relationships/>",
            "xl/threadedComments/threadedComment1.xml":
                b'<ThreadedComments><threadedComment ref="B2" personId="P1">'
                b"<text>Check this</text></threadedComment></ThreadedComments>",
        })
        roots = parse_xlsx_comments(data)

        assert [r["ref"] for r in roots] == ["B2"]
        assert roots[0]["text"] == "Check this"

    def test_a_member_over_the_size_budget_is_skipped_not_read(self):
        """The bomb case. A declared size can lie, but only downwards, so the cheap header
        check removes the cheap attack - and skipping is the whole point: the parse continues
        with what it could afford."""
        from csa_google_workspace import _cellmap

        data = self.book({
            "xl/workbook.xml": b"<workbook/>",
            "_rels/.rels": b"<Relationships/>",
            "xl/persons/person.xml": b"<personList/>",
            "xl/threadedComments/threadedComment1.xml":
                b'<ThreadedComments><threadedComment ref="C3">'
                b"<text>Still here</text></threadedComment></ThreadedComments>",
        })
        # One byte of budget: every member is over it, so every read is skipped.
        original = _cellmap._MAX_MEMBER_UNCOMPRESSED
        try:
            _cellmap._MAX_MEMBER_UNCOMPRESSED = 1
            roots = _cellmap.parse_xlsx_comments(data)
        finally:
            _cellmap._MAX_MEMBER_UNCOMPRESSED = original

        assert roots == [], "nothing was read, and nothing raised"

    def test_a_comment_with_no_text_element_still_produces_a_row(self):
        """A `threadedComment` whose children are all something else - a mention, a formatting
        run. An empty `text` is honest; dropping the row would lose the cell reference, which
        is the part a register is built on."""
        from csa_google_workspace._cellmap import parse_xlsx_comments

        data = self.book({
            "xl/workbook.xml": b"<workbook/>",
            "_rels/.rels": b"<Relationships/>",
            "xl/threadedComments/threadedComment1.xml":
                b'<ThreadedComments><threadedComment ref="D4">'
                b"<mentions/></threadedComment></ThreadedComments>",
        })
        roots = parse_xlsx_comments(data)

        assert [r["ref"] for r in roots] == ["D4"]
        assert roots[0]["text"] == ""

    def test_a_sheet_or_relationship_that_is_half_there_maps_nothing(self):
        """Both halves are needed at each hop. A `sheet` with a name and no id, or an id and
        no name, cannot be paired with anything - and keying the map on `None` would attach
        every unnamed sheet's comments to one another. Likewise a `Relationship` whose id
        matches no sheet: it is one of the several a workbook carries for styles and themes.

        The comment still comes back, WITHOUT a tab. That is the documented posture: a part
        missing from the result means "sheet unknown", which is not the same as "the first
        sheet", and filling it with a plausible default is the failure this walk exists to
        avoid (probed 2026-08-31 - a real Google export numbers the first sheet `rId5`)."""
        from csa_google_workspace._cellmap import parse_xlsx_comments

        data = self.book({
            "xl/workbook.xml": b'<workbook><sheets><sheet name="OnlyAName"/>'
                               b'<sheet id="rId1"/></sheets></workbook>',
            # rId9 matches no sheet: a styles or theme relationship, which every workbook has.
            "xl/_rels/workbook.xml.rels":
                b'<Relationships><Relationship Id="rId9" Target="styles.xml"/>'
                b"</Relationships>",
            "xl/threadedComments/threadedComment1.xml":
                b'<ThreadedComments><threadedComment ref="A1">'
                b"<text>Hi</text></threadedComment></ThreadedComments>",
        })
        roots = parse_xlsx_comments(data)

        assert [r["ref"] for r in roots] == ["A1"]
        assert roots[0].get("tab") is None, "a tab was invented for an unresolvable sheet"


class TestTheVariableThatWasSplitInTwo:
    def test_the_retired_name_is_refused_and_names_both_replacements(self):
        """Refusing to guess. Treating it as the modify list would leave `read` fail-closed
        and break reads for reasons nobody could see; an error naming both costs one restart."""
        from csa_google_workspace.allowlist import AllowlistError
        from csa_google_workspace.mcp._config import settings_from_env

        with pytest.raises(AllowlistError) as ei:
            settings_from_env({"CSA_GW_ALLOWLIST": "https://docs.google.com/document/d/A/edit"})

        message = str(ei.value)
        assert "CSA_GW_ALLOWLIST_READ" in message and "CSA_GW_ALLOWLIST_MODIFY" in message
        assert "Refusing to guess" in message

    def test_the_two_new_names_are_accepted(self):
        from csa_google_workspace.mcp._config import settings_from_env

        settings = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*",
                                      "CSA_GW_ALLOWLIST_MODIFY": "*"})
        assert settings.policy is not None


class TestTheCommandNameInAMessage:
    def test_a_path_like_argv0_is_used_verbatim(self, monkeypatch):
        """The message says what to RUN, and a pipx install's script is not on the PATH of
        whatever launched the server. When argv[0] is a path, it is the one that works."""
        import sys

        from csa_google_workspace.mcp import _config

        monkeypatch.setattr(sys, "argv", ["/opt/pipx/bin/csa-google-workspace-mcp"])
        assert _config._launcher() == "/opt/pipx/bin/csa-google-workspace-mcp"

    def test_a_bare_argv0_falls_back_to_the_published_name(self, monkeypatch):
        """`python -m`, a test runner, an embedder. `sys.argv[0]` is then something the reader
        cannot type, so the published console-script name is the better instruction."""
        import sys

        from csa_google_workspace.mcp import _config

        monkeypatch.setattr(sys, "argv", ["pytest"])
        assert _config._launcher() == "csa-google-workspace-mcp"


class TestStartupWarningsWithNoPolicy:
    def test_no_policy_means_no_warnings_rather_than_a_crash(self):
        """`Settings` can be built without one - a library embedder, a test. The warnings are
        derived from the policy, so there is nothing to say and nothing to raise about."""
        from csa_google_workspace.mcp._config import Settings, startup_warnings

        assert startup_warnings(Settings(policy=None)) == []


class TestFailingClosedRatherThanGuessing:
    def test_a_file_scoped_call_with_no_file_id_is_refused_as_a_bug(self):
        """The allowlist cannot be applied to a call it cannot attribute to a file. Letting it
        through would be an unchecked call; guessing an id would be worse. The message says
        "this is a bug" because the fix is the gate table or the call site, not a wider
        policy - which is what somebody reaches for when a refusal looks like configuration."""
        from csa_google_workspace.mcp._config import settings_from_env
        from csa_google_workspace.policy import PolicyBackend

        settings = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*",
                                      "CSA_GW_ALLOWLIST_MODIFY": "*"})
        gated = PolicyBackend(FakeBackend({}), settings.policy)

        with pytest.raises(exc.UnsupportedOperation) as ei:
            gated.get_file_metadata()

        assert "file-scoped" in str(ei.value) and "This is a bug" in str(ei.value)


class TestFilteringAListingThatLosesNothing:
    def test_a_result_entirely_inside_the_allowlist_passes_through_unchanged(self):
        """The quiet path, and the one worth pinning: a filter that logged on every call would
        make "results were removed" unfindable in the noise."""
        from csa_google_workspace.policy import PolicyBackend, Scope

        result = {"files": [{"id": "a"}, {"id": "b"}]}
        scope = Scope(all_files=False, ids=frozenset({"a", "b"}))

        assert PolicyBackend._filter_listing("search_files", result, scope) == result

    def test_a_result_partly_outside_it_is_trimmed(self):
        from csa_google_workspace.policy import PolicyBackend, Scope

        result = {"files": [{"id": "a"}, {"id": "elsewhere"}]}
        scope = Scope(all_files=False, ids=frozenset({"a"}))
        filtered = PolicyBackend._filter_listing("search_files", result, scope)

        assert filtered["files"] == [{"id": "a"}]


class TestSuggestionsInsideATable:
    def test_a_table_with_no_rows_contributes_nothing(self):
        """An empty table is a real element in a Doc. Walking into it must terminate rather
        than assume there is a row to descend into."""
        from csa_google_workspace import suggestions

        groups: dict = {}
        suggestions._collect({"table": {"tableRows": []}}, groups)
        assert groups == {}

    def test_a_suggestion_inside_a_table_cell_is_found(self):
        """The reason the walk recurses at all. A suggested edit in a table would otherwise be
        invisible to `list_suggestions`, which is the tool somebody uses to decide whether a
        document is ready."""
        from csa_google_workspace import suggestions

        groups: dict = {}
        suggestions._collect({"table": {"tableRows": [{"tableCells": [{"content": [
            {"paragraph": {"elements": [{"textRun": {
                "content": "added", "suggestedInsertionIds": ["s1"]}}]}},
        ]}]}]}}, groups)

        assert groups, "a suggestion inside a table cell was not found"


class TestAnUnreadableTokenIsNotAnError:
    def test_a_missing_or_malformed_token_yields_no_client_id(self, tmp_path):
        """`login` compares the cached token's OAuth client against the one it is about to
        use, so it can warn about a token minted by a different project. That comparison is a
        COURTESY - it must never stop a login, so anything unreadable is simply "unknown"."""
        from csa_google_workspace.mcp._login import _token_client_id

        missing = tmp_path / "absent.json"
        malformed = tmp_path / "bad.json"
        malformed.write_text("{not json", encoding="utf-8")

        assert _token_client_id(str(missing)) is None
        assert _token_client_id(str(malformed)) is None

    def test_a_readable_token_gives_its_client_id(self, tmp_path):
        import json

        from csa_google_workspace.mcp._login import _token_client_id

        path = tmp_path / "token.json"
        path.write_text(json.dumps({"client_id": "111-abc.apps.googleusercontent.com"}),
                        encoding="utf-8")
        assert _token_client_id(str(path)) == "111-abc.apps.googleusercontent.com"


class TestPreviewingTheAllowlistThroughTheTool:
    def test_it_resolves_each_entry_against_drive_and_reports_what_it_found(self):
        """`preview_allowlist` is what an operator runs to check a list they just wrote. The
        answer has to come from DRIVE - a dead entry is one whose id no longer resolves, and
        only a fetch can say so."""
        import asyncio

        from csa_google_workspace.mcp._config import settings_from_env
        from csa_google_workspace.mcp.server import create_server

        alive = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"
        url = f"https://docs.google.com/document/d/{alive}/edit"
        backend = FakeBackend({alive: {"id": alive, "name": "Live Doc", "mimeType": DOC_MIME}})
        app = create_server(lambda: Workspace(backend), settings=settings_from_env(
            {"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": url}))

        out = asyncio.run(app.call_tool("preview_allowlist", {})).structured_content

        assert out["read"]["unrestricted"] is True
        assert out["modify"]["entries"][0]["name"] == "Live Doc"
        assert out["dead_entries"] == 0


class TestTheRemainingTwoLoops:
    def test_a_table_cell_with_no_content_completes_the_walk(self):
        """The innermost loop of the suggestion walk, running out. A cell with an empty
        `content` list is ordinary - a blank cell in a table - and the walk has to finish
        rather than assume there is something to descend into."""
        from csa_google_workspace import suggestions

        groups: dict = {}
        suggestions._collect(
            {"table": {"tableRows": [{"tableCells": [{"content": []}]}]}}, groups)
        assert groups == {}

    def test_an_element_that_is_neither_a_paragraph_nor_a_table_ends_the_walk(self):
        """A section break, a table of contents, an embedded object. Neither branch fires and
        the function simply returns - which is the whole of what it should do, and is only
        visible as a branch that has to be able to fall through."""
        from csa_google_workspace import suggestions

        groups: dict = {}
        suggestions._collect({"sectionBreak": {"sectionStyle": {}}}, groups)
        suggestions._collect({}, groups)
        assert groups == {}

    def test_a_file_type_with_no_text_extraction_still_returns_its_metadata(self):
        """`getattr`, not `_require`. A folder or an uploaded PDF has no `as_text`, and
        failing the whole call over the SNIPPET would lose the name, the type and the link -
        which is most of what `get_file_metadata` is for."""
        import asyncio

        from csa_google_workspace.mcp._config import settings_from_env
        from csa_google_workspace.mcp.server import create_server

        folder = "folder1"
        backend = FakeBackend({folder: {"id": folder, "name": "Archive",
                                        "mimeType": "application/vnd.google-apps.folder",
                                        "webViewLink": "u"}})
        app = create_server(lambda: Workspace(backend),
                            settings=settings_from_env({"CSA_GW_ALLOWLIST_READ": "*"}))

        out = asyncio.run(app.call_tool(
            "get_file_metadata", {"fileId": folder})).structured_content

        assert out["name"] == "Archive"
        assert out.get("content_snippet") is None


class TestAMatchOnNameAloneIsCountedSeparately:
    """A display-name match is a GUESS - names are neither unique nor stable - and an email
    match is an identity. The count is what lets the register's caveat say how many rows rest
    on the weaker one, which is the difference between a sweep somebody can act on and one
    they have to re-check by hand.

    It is counted in TWO places, and the comment-author one had never run: a file can be
    attributed to the subject because they last edited it, or because they wrote a comment on
    it, and both are name matches when Drive gave no address.
    """

    @staticmethod
    def ref(file_id, modifier=None):
        return type("Ref", (), {
            "id": file_id, "owners": None, "last_modifying_user": modifier,
            "openable": True, "name": "D", "type": "document", "url": "u",
            "modified_time": None, "created_time": None, "size": None,
            "trashed": False, "shared": False, "drive_id": None})()

    @staticmethod
    def comment_by(display_name, email=None):
        author = type("Author", (), {"display_name": display_name, "email": email,
                                     "me": False})()
        return type("Comment", (), {"author": author})()

    def test_a_comment_author_matched_by_name_alone_is_counted(self):
        from csa_google_workspace import _inventory

        built = _inventory.build(
            [self.ref("f1")], subject="Away Person",
            comments_by_file={"f1": [self.comment_by("Away Person")]}, unreachable=[])

        assert any("DISPLAY NAME" in c for c in built.caveats)

    def test_a_comment_author_matched_by_address_is_not_counted(self):
        """The mirror, and the one that keeps the caveat meaningful. If every match counted,
        the warning would fire on every sweep and stop being read."""
        from csa_google_workspace import _inventory

        built = _inventory.build(
            [self.ref("f1")], subject="away@example.org",
            comments_by_file={"f1": [self.comment_by("Away Person", "away@example.org")]},
            unreachable=[])

        assert not any("DISPLAY NAME" in c for c in built.caveats)

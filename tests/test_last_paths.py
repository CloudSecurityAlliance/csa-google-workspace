"""The remaining branches, grouped by what they protect rather than by module.

Three themes run through them:

**Failing closed where a decision is missing.** `PolicyBackend` refuses a method with no gate
and a file-scoped call with no file id, rather than letting either through. Both messages say
"this is a bug", because they are: the right fix is a gate or an argument, not a wider policy.

**Refusing input that would succeed and mean nothing.** An empty `values` list writes no cells
and reports success; a row that is not a list becomes a cell containing the repr of a list.

**Answering with what is there.** A parser handed a shape it does not recognise returns a
usable default rather than raising, because it runs inside an export somebody is waiting for.
"""
from __future__ import annotations

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace import exceptions as exc
from csa_google_workspace.backend import FakeBackend

DOC_MIME = "application/vnd.google-apps.document"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"


class TestFailingClosedWhenNobodyDecided:
    """`PolicyBackend` is the seam every call crosses. Two states there are bugs rather than
    configurations, and both refuse rather than guess."""

    @staticmethod
    def gated():
        from csa_google_workspace.mcp._config import settings_from_env
        from csa_google_workspace.policy import PolicyBackend

        settings = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*",
                                      "CSA_GW_ALLOWLIST_MODIFY": "*"})
        backend = FakeBackend({"f": {"id": "f", "name": "D", "mimeType": DOC_MIME}})
        return PolicyBackend(backend, settings.policy)

    def test_a_method_with_no_gate_is_refused_not_passed_through(self):
        """An unlisted method is one whose gate nobody decided. Passing it through would make
        the policy silently incomplete - every method added after the gate table was written
        would be ungoverned, and nothing would say which ones."""
        with pytest.raises(exc.UnsupportedOperation):
            self.gated().some_method_nobody_gated("f")

    def test_a_private_name_is_an_attribute_error_not_a_policy_refusal(self):
        """`_backend`, `__deepcopy__`, `_ipython_canary_...`. Turning those into policy
        refusals would make ordinary Python introspection look like a security event."""
        private = "_not_a_real_attribute"          # via a name, so ruff sees a real lookup
        with pytest.raises(AttributeError):
            getattr(self.gated(), private)


class TestRefusingInputThatWouldSucceedAndMeanNothing:
    """`update_cells` and `append_rows` both take a list of rows. Two shapes get through the
    JSON schema and produce nonsense at the other end."""

    @staticmethod
    def call(name, **args):
        import asyncio

        from csa_google_workspace.mcp._config import settings_from_env
        from csa_google_workspace.mcp.server import create_server
        from csa_google_workspace.policy import PolicyBackend

        settings = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*",
                                      "CSA_GW_ALLOWLIST_MODIFY": "*",
                                      "CSA_GW_PROFILE": "full"})
        backend = FakeBackend(
            {"s1": {"id": "s1", "name": "Book", "mimeType": SHEET_MIME}},
            spreadsheets={"s1": {"sheets": [{"properties": {"title": "Sheet1",
                                                            "sheetId": 0}}]}})
        app = create_server(lambda: Workspace(PolicyBackend(backend, settings.policy)),
                            settings=settings)
        return asyncio.run(app.call_tool(name, {"fileId": "s1", **args}))

    @pytest.mark.parametrize("tool", ["update_cells", "append_rows"])
    def test_an_empty_values_list_is_refused_rather_than_reported_as_a_write(self, tool):
        """`[]` satisfies `list[list[Any]]`, so the JSON schema lets it through. Without the
        guard the call writes no cells, returns `cells: 0`, and reports success - and the
        caller's next move is to believe the data is there."""
        with pytest.raises(Exception) as ei:
            self.call(tool, a1Range="Sheet1!A1", values=[])
        assert "list of rows" in str(ei.value)

    @pytest.mark.parametrize("tool", ["update_cells", "append_rows"])
    @pytest.mark.parametrize("values", [["a", "b"], [["ok"], "not a row"]],
                             ids=["flat-strings", "one-bad-row"])
    def test_rows_that_are_not_lists_never_reach_the_tool_body(self, tool, values):
        """The OTHER half of the guard, and it is the SDK that enforces it: `values` is typed
        `list[list[Any]]`, so a flat list of strings is rejected as a schema violation before
        the function runs.

        Worth a test anyway, because what it prevents is not a crash. Sheets ACCEPTS a flat
        list: each string becomes a row of one cell. The write succeeds, the caller is told it
        succeeded, and the spreadsheet is wrong in a way only somebody looking at it notices.
        The guard in the body stays as the library-level backstop, since `Sheet.update` is
        callable without the server."""
        from mcp.server.mcpserver.exceptions import ToolError

        with pytest.raises((ToolError, ValueError)):
            self.call(tool, a1Range="Sheet1!A1", values=values)

    @pytest.mark.parametrize("tool", ["update_cells", "append_rows"])
    def test_a_proper_grid_is_accepted(self, tool):
        """The refusal has to be about the SHAPE, not about writing."""
        assert self.call(tool, a1Range="Sheet1!A1", values=[["a", "b"], ["c", "d"]])


class TestAskingForAResourceThatIsNotPublished:
    def test_the_refusal_lists_what_is(self):
        """A model guessing at a URI is the expected case - it read one in a tool description
        and typed it from memory. Listing the real ones turns the refusal into the answer, and
        this tool exists because a client without resource support cannot browse them."""
        import asyncio

        from mcp.server.mcpserver.exceptions import ToolError

        from csa_google_workspace.mcp._config import settings_from_env
        from csa_google_workspace.mcp.server import create_server

        app = create_server(lambda: Workspace(FakeBackend({})),
                            settings=settings_from_env({"CSA_GW_ALLOWLIST_READ": "*"}))
        with pytest.raises(ToolError) as ei:
            asyncio.run(app.call_tool("read_server_resource", {"uri": "csa-gw://nope"}))

        message = str(ei.value)
        assert "no such resource" in message
        assert "csa-gw://config" in message, "the refusal must name what IS published"


class TestParsersThatAnswerRatherThanRaise:
    def test_a_cell_reference_in_no_shape_it_knows_keeps_the_text(self):
        """An .xlsx can carry a ref this parser does not understand - a defined name, a
        cross-sheet reference. Keeping the raw text and reporting row 0 says "here is what the
        file said, and we could not place it", which is more useful in a register than a
        missing row, and honest about which half failed."""
        from csa_google_workspace._cellmap import location_from_ref

        location = location_from_ref("NamedRange", "Sheet1")
        assert location.cell == "NamedRange"
        assert location.row == 0 and location.col == 0
        assert location.tab == "Sheet1"

    def test_an_ordinary_reference_still_parses(self):
        from csa_google_workspace._cellmap import location_from_ref

        location = location_from_ref("AB12", "Sheet1")
        assert (location.row, location.col) == (12, 28)

    def test_an_absolute_zip_path_is_taken_from_the_archive_root(self):
        """An .xlsx relationship target may be absolute. Joining it onto the part's directory
        would produce a key matching nothing, and the tab would silently come back None -
        which reads as "this comment is not on a sheet" rather than "we could not resolve it"."""
        from csa_google_workspace._cellmap import _resolve

        assert _resolve("xl/worksheets/_rels", "/xl/worksheets/sheet1.xml") == \
            "xl/worksheets/sheet1.xml"

    def test_a_relative_target_is_joined_and_normalised(self):
        from csa_google_workspace._cellmap import _resolve

        assert _resolve("xl/worksheets/_rels", "../sheet1.xml") == "xl/worksheets/sheet1.xml"


class TestTheConsoleEntryPoints:
    def test_the_package_main_delegates_to_the_cli_and_exits_with_its_code(self, monkeypatch):
        """`main` is what `pip install` wires to the console script. It is imported lazily so
        `[mcp]` stays optional, which means nothing else in the package references it - and
        a broken one is only discovered by somebody running the installed command."""
        from csa_google_workspace import mcp

        monkeypatch.setattr("csa_google_workspace.mcp.cli.main", lambda: 3)
        with pytest.raises(SystemExit) as ei:
            mcp.main()
        assert ei.value.code == 3

    def test_python_dash_m_reaches_the_same_place(self, monkeypatch):
        """`python -m csa_google_workspace.mcp` is `launch_command`'s last-resort form, so it
        is the one a Claude Desktop config falls back to - and the only entry point with no
        console script to keep it honest."""
        import runpy

        called = {}
        monkeypatch.setattr("csa_google_workspace.mcp.cli.main",
                            lambda: (called.update(ran=True), 0)[1])
        with pytest.raises(SystemExit) as ei:
            runpy.run_module("csa_google_workspace.mcp.__main__", run_name="__main__")

        assert called.get("ran") is True
        assert ei.value.code == 0


class TestServicesAreBuiltOneAtATime:
    def test_each_api_is_built_on_first_use_and_then_reused(self, monkeypatch):
        """Four Google clients - drive, docs, sheets, slides, drivelabels - and a session may
        touch one. Building them all at startup costs a discovery fetch each, which is time
        the MCP client spends waiting before the first tool call."""
        from csa_google_workspace._services import ServiceRegistry

        built = []
        holder = ServiceRegistry(credentials=object(),
                                 builder=lambda name, version, credentials: (
                                     built.append(name) or name))

        assert holder.sheets == "sheets"
        assert holder.slides == "slides"
        assert holder.drivelabels == "drivelabels"
        assert built == ["sheets", "slides", "drivelabels"], "an unused API was built"

        assert holder.sheets == "sheets"
        assert built.count("sheets") == 1, "the client was rebuilt on second use"

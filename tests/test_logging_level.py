"""Diagnostics reach stderr at a level you can set, and never carry document content.

**#145, rescoped.** This was specced as a logging subsystem — JSONL writer, log directory,
session ids, retention, `0600` — until somebody checked whether the MCP client was already doing
it. It was: Claude Code keeps per-connection JSONL with a `sessionId` under
`~/Library/Caches/claude-cli-nodejs/`, capturing our stderr **verbatim**, and Claude Desktop does
the same independently in a different format. Two clients, not coordinating.

Their version is also better than one written here — it is the *parent* capturing the *child*, so
it survives the server failing to start, crashing, or hanging, which is when a log is most wanted
and when a self-written file is missing. So the whole feature collapsed to **a level, and what to
say.** Full write-up: `CINO-Engineering/research/mcp-servers/
LOGGING-BELONGS-TO-THE-CLIENT.md`.

Three properties are worth holding, and they are the three that would be expensive to get wrong:

1. **Nothing reaches stdout.** Under stdio that IS the JSON-RPC channel; one stray line corrupts
   the session and looks like a hung server from the client end. This repository has had one.
2. **No document or comment content is logged, at any level.** The client's free persistence makes
   this stricter rather than looser — our stderr lands in a cache directory we cannot see or
   purge, so a debug log of untrusted content is a persistence step for an injection payload.
3. **Only an application configures logging.** A library that attaches handlers hijacks its
   embedder's configuration, and this is a library first.
"""
from __future__ import annotations

import asyncio
import io
import logging
import sys

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import _logging, settings_from_env
from csa_google_workspace.mcp.server import create_server

DOC = "doc1"
MIME = "application/vnd.google-apps.document"
SECRET = "PAYROLL FIGURES ARE 12345 AND ceo@example.com SAID SO"


def server():
    backend = FakeBackend(
        {DOC: {"id": DOC, "name": "A Doc", "mimeType": MIME}},
        documents={DOC: {"body": {"content": [
            {"paragraph": {"elements": [{"textRun": {"content": SECRET}}]}}]}}},
        comments={DOC: [{"id": "c1", "content": SECRET,
                         "author": {"displayName": "Reviewer"}}]})
    return create_server(lambda: Workspace(backend),
                         settings=settings_from_env({"CSA_GW_PROFILE": "organizer"}))


@pytest.fixture
def captured(monkeypatch):
    """Attach our handler to a buffer instead of stderr, and restore afterwards.

    Deliberately exercises `_logging.configure` rather than hand-rolling a handler, so the test
    covers the thing that ships.
    """
    stream = io.StringIO()
    _logging.configure({"CSA_GW_LOG_LEVEL": "DEBUG"})
    logger = logging.getLogger("csa_google_workspace")
    for handler in logger.handlers:
        if getattr(handler, "_csa_gw", False):
            handler.setStream(stream)
    yield stream
    for handler in list(logger.handlers):
        if getattr(handler, "_csa_gw", False):
            logger.removeHandler(handler)


class TestTheLevel:
    def test_it_defaults_to_warning(self):
        """Quiet unless something is wrong. Somebody who installs this and never configures
        anything should not have their client's log filled with routine calls."""
        assert _logging.level_from_env({}) == "WARNING"

    @pytest.mark.parametrize("spelling", ["debug", "DEBUG", "  Debug "])
    def test_the_value_is_case_and_space_insensitive(self, spelling):
        assert _logging.level_from_env({"CSA_GW_LOG_LEVEL": spelling}) == "DEBUG"

    def test_an_unknown_level_is_an_error_rather_than_a_silent_default(self):
        """The failure mode of falling back: somebody sets `LOG_LEVEL=verbose` to diagnose a
        problem, sees no extra output, and concludes the tool has nothing more to say."""
        with pytest.raises(ValueError) as e:
            _logging.level_from_env({"CSA_GW_LOG_LEVEL": "verbose"})
        assert "DEBUG" in str(e.value), "the refusal must name the values that work"

    def test_only_pythons_five_levels_exist_here(self):
        """MCP's own logging capability uses syslog's eight, including `notice`, `alert` and
        `emergency`. That is the `ctx.log` channel, whose level the CLIENT sets at runtime. This
        variable governs our stderr, so it speaks Python — and nothing in a document-editing
        server is a paging event."""
        assert _logging.LEVELS == ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class TestConfiguringIsIdempotentAndScoped:
    def test_calling_it_twice_does_not_duplicate_the_handler(self):
        """`login` and the server share an entry point. A doubled handler prints everything
        twice, which reads like a retry loop."""
        logger = logging.getLogger("csa_google_workspace")
        before = len(logger.handlers)
        _logging.configure({})
        _logging.configure({})
        ours = [h for h in logger.handlers if getattr(h, "_csa_gw", False)]
        assert len(ours) == 1, f"{len(ours)} handlers attached (was {before})"
        for handler in ours:
            logger.removeHandler(handler)

    def test_it_touches_this_package_and_not_the_root_logger(self):
        """A library that configures root hijacks its embedder. `Workspace` inside somebody's
        application must leave their logging alone."""
        root_before = list(logging.getLogger().handlers)
        _logging.configure({})
        assert logging.getLogger().handlers == root_before
        logger = logging.getLogger("csa_google_workspace")
        assert not logger.propagate, (
            "records must not reach a handler this process did not install")
        for handler in list(logger.handlers):
            if getattr(handler, "_csa_gw", False):
                logger.removeHandler(handler)

    def test_the_library_configures_nothing_on_import(self):
        """Importing the package must not attach anything. Only `cli.main` configures."""
        import importlib

        for name in ("csa_google_workspace", "csa_google_workspace.policy"):
            importlib.import_module(name)
        logger = logging.getLogger("csa_google_workspace")
        assert not [h for h in logger.handlers if getattr(h, "_csa_gw", False)]


class TestNothingReachesStdout:
    """The failure this repository has already had once, and the reason the whole arrangement
    works: stderr is free precisely because stdout is reserved."""

    def test_a_tool_call_writes_nothing_to_stdout(self, captured, monkeypatch):
        out = io.StringIO()
        monkeypatch.setattr(sys, "stdout", out)
        asyncio.run(server().call_tool("get_file_metadata", {"fileId": DOC}))
        assert out.getvalue() == "", f"bytes on stdout: {out.getvalue()[:200]!r}"

    def test_the_handler_is_bound_to_stderr(self):
        _logging.configure({})
        logger = logging.getLogger("csa_google_workspace")
        ours = [h for h in logger.handlers if getattr(h, "_csa_gw", False)]
        assert ours and ours[0].stream is sys.stderr
        for handler in ours:
            logger.removeHandler(handler)


class TestTheOperationIsLoggedAndTheContentIsNot:
    """The rule the client's free persistence makes stricter: raising the level raises detail
    about the OPERATION, never about the CONTENT."""

    def test_a_successful_call_records_the_tool_and_the_file(self, captured):
        asyncio.run(server().call_tool("get_file_metadata", {"fileId": DOC}))
        text = captured.getvalue()
        assert "get_file_metadata" in text and DOC in text
        assert "ms" in text, "the duration is the point of an INFO line"

    @pytest.mark.parametrize("tool,args", [
        ("read_file_content", {"fileId": DOC}),
        ("list_comments", {"fileId": DOC}),
        ("create_comment", {"fileId": DOC, "content": SECRET}),
        ("replace_text", {"fileId": DOC, "find": SECRET, "replace": SECRET}),
    ])
    def test_no_document_or_comment_content_reaches_the_log(self, captured, tool, args):
        """Covers both directions: content READ back from a document, and content passed IN as
        an argument. The second is the one a debug-logging habit would leak — `create_comment`
        carries comment text and `replace_text` carries a replacement."""
        try:
            asyncio.run(server().call_tool(tool, args))
        except Exception:
            pass                                   # a refusal still must not log the content
        text = captured.getvalue()
        assert SECRET not in text, f"{tool} logged content: {text[:300]!r}"
        assert "PAYROLL" not in text and "ceo@example.com" not in text

    def test_a_refusal_is_recorded_with_its_reason(self, captured):
        """The reason is the one the caller already receives, so this adds no exposure — it makes
        the refusal visible to whoever reads the log rather than only to the model."""
        try:
            asyncio.run(server().call_tool("get_file_metadata", {"fileId": "nope"}))
        except Exception:
            pass
        text = captured.getvalue()
        assert "refused" in text and "get_file_metadata" in text

    def test_an_expected_refusal_is_info_not_warning(self, captured):
        """A missing file or a policy refusal is the system working. Logging those as warnings
        makes a correctly-configured server look unhealthy, and a log that cries wolf gets
        filtered — taking the real warnings with it."""
        try:
            asyncio.run(server().call_tool("get_file_metadata", {"fileId": "nope"}))
        except Exception:
            pass
        line = [ln for ln in captured.getvalue().splitlines() if "refused" in ln]
        assert line and line[0].startswith("INFO"), line

    def test_nothing_is_emitted_at_the_default_level_for_a_normal_call(self, monkeypatch):
        """"Quiet by default" asserted rather than assumed: at WARNING a successful call must
        produce no output at all."""
        stream = io.StringIO()
        _logging.configure({})                     # default WARNING
        logger = logging.getLogger("csa_google_workspace")
        for handler in logger.handlers:
            if getattr(handler, "_csa_gw", False):
                handler.setStream(stream)
        try:
            asyncio.run(server().call_tool("get_file_metadata", {"fileId": DOC}))
            assert stream.getvalue() == "", f"noisy at WARNING: {stream.getvalue()[:200]!r}"
        finally:
            for handler in list(logger.handlers):
                if getattr(handler, "_csa_gw", False):
                    logger.removeHandler(handler)


class TestExceptionMessagesAreNotLoggedBelowTheBoundaryEither:
    """The library's own `WARNING` sites log the exception TYPE, never its message.

    **The audit's F7 note on T39 was that `tests/test_logging_level.py` asserts the
    operation-never-content property against `FakeBackend`, which cannot produce the failing
    values.** That was accurate, and it is why the defect survived here: the tests above drive a
    fake whose exceptions carry nothing worth redacting.

    #313 closed the MCP boundary — `_base.py` logs `type(e).__name__` on every path. But
    `Sheet._cell_map` sits **below** that boundary, so the boundary fix never reached it, and it
    was logging `e` at WARNING: a `CsaWorkspaceError` arriving there can carry a tab-title list,
    and `sheet.py` builds exactly such messages elsewhere (`present: ['Q3 Layoff Plan', …]`).

    So this drives a backend that DOES raise a content-bearing exception on that path. T39 is
    recorded as `mitigated` in `THREAT_MODEL.md`, and this is what makes that claim checkable
    rather than asserted.
    """

    SHEET = "application/vnd.google-apps.spreadsheet"
    SECRET = "Q3 Layoff Plan"

    def a_sheet_whose_export_fails_with_content(self):
        from csa_google_workspace import Workspace
        from csa_google_workspace import exceptions as exc
        from csa_google_workspace.backend import FakeBackend

        secret = self.SECRET

        class LeakyExport(FakeBackend):
            def export_file(self, file_id, mime_type):
                raise exc.NotFoundError(f"no tab named 'x'; present: ['{secret}']")

        be = LeakyExport({"s": {"id": "s", "name": "Grid", "mimeType": self.SHEET}},
                         comments={"s": [{"id": "c1", "content": "hi",
                                          "author": {"displayName": "A"}}]})
        return Workspace(be).open("s")

    def test_the_tab_title_does_not_reach_the_log(self, caplog):
        sheet = self.a_sheet_whose_export_fails_with_content()
        with caplog.at_level(logging.DEBUG, logger="csa_google_workspace"):
            list(sheet.comments)          # drives _cell_map, which swallows and warns
        assert caplog.text, "nothing was logged, so this assertion would pass vacuously"
        assert self.SECRET not in caplog.text, (
            "a tab title reached a log this process cannot rotate or purge (T39)")

    def test_but_the_exception_TYPE_still_is(self, caplog):
        """The operation detail has to survive, or the fix is just deleting the diagnostic."""
        sheet = self.a_sheet_whose_export_fails_with_content()
        with caplog.at_level(logging.DEBUG, logger="csa_google_workspace"):
            list(sheet.comments)
        assert "NotFoundError" in caplog.text
        assert "cell mapping unavailable" in caplog.text

    def test_and_the_degrade_still_happens(self, caplog):
        """Losing the message must not change the behaviour it was describing: the comments
        still come back, with no location, rather than the call failing."""
        sheet = self.a_sheet_whose_export_fails_with_content()
        with caplog.at_level(logging.DEBUG, logger="csa_google_workspace"):
            comments = list(sheet.comments)
        assert [c.id for c in comments] == ["c1"]
        assert comments[0].location is None

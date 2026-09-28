"""Acting on ONE REPLY rather than a whole thread, and the two switches around the register.

`edit_comment` and `delete_comment` take an optional `replyId`, and that argument is the
difference between changing one person's sentence and removing an entire conversation. Neither
branch had been executed through the MCP layer.

Deleting a thread takes every reply on it with it, including other people's, and Drive strips
their text and authors permanently. So "the reply is not on this comment" has to be an error
rather than a fall-through to the thread - a fall-through would silently widen a targeted
delete into a destructive one.
"""
from __future__ import annotations

import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server
from csa_google_workspace.policy import PolicyBackend

DOC = "d1"
DOC_MIME = "application/vnd.google-apps.document"


def build(**env):
    comments = {DOC: [{
        "id": "t1", "content": "The original point", "author": {"displayName": "A"},
        "createdTime": "2026-08-20T10:00:00Z", "resolved": False,
        "replies": [
            {"id": "r1", "content": "First reply", "author": {"displayName": "B"},
             "createdTime": "2026-08-20T11:00:00Z"},
            {"id": "r2", "content": "Second reply", "author": {"displayName": "C"},
             "createdTime": "2026-08-20T12:00:00Z"},
        ]}]}
    backend = FakeBackend({DOC: {"id": DOC, "name": "Draft", "mimeType": DOC_MIME}},
                          documents={DOC: {"body": {"content": []}}}, comments=comments)
    st = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
                            "CSA_GW_PROFILE": "full", **env})
    return create_server(lambda: Workspace(PolicyBackend(backend, st.policy)), settings=st)


def call(app, name, **args):
    return asyncio.run(app.call_tool(name, {"fileId": DOC, **args})).structured_content


def replies(out):
    return {r["id"]: r["content"] for r in out["replies"]}


class TestEditingOneReply:
    def test_a_reply_id_edits_that_reply_and_leaves_the_thread_alone(self):
        app = build()
        out = call(app, "edit_comment", commentId="t1", replyId="r1", content="Reworded")

        assert replies(out)["r1"] == "Reworded"
        assert replies(out)["r2"] == "Second reply", "the other reply was touched"
        assert out["content"] == "The original point", "the thread's own text was touched"

    def test_no_reply_id_edits_the_thread_itself(self):
        app = build()
        out = call(app, "edit_comment", commentId="t1", content="Rewritten opening")

        assert out["content"] == "Rewritten opening"
        assert replies(out) == {"r1": "First reply", "r2": "Second reply"}

    def test_a_reply_that_is_not_on_this_comment_is_an_error_not_a_fall_through(self):
        """Falling through to the thread would rewrite the WRONG person's text - and the
        caller, having named a reply, would read the success as having edited it."""
        with pytest.raises(ToolError) as ei:
            call(build(), "edit_comment", commentId="t1", replyId="r-elsewhere",
                 content="Reworded")
        assert "r-elsewhere" in str(ei.value) and "t1" in str(ei.value)

    def test_nothing_changed_when_the_reply_was_not_found(self):
        """The refusal is before the edit, so a mistyped id costs a message rather than
        somebody's paragraph."""
        app = build()
        with pytest.raises(ToolError):
            call(app, "edit_comment", commentId="t1", replyId="nope", content="Reworded")

        after = call(app, "get_comment", commentId="t1")
        assert after["content"] == "The original point"
        assert replies(after) == {"r1": "First reply", "r2": "Second reply"}


class TestDeletingOneReply:
    def test_a_reply_id_removes_only_that_reply(self):
        """The whole point of the argument, and the reply's remains are the evidence.

        A deleted reply is a TOMBSTONE, not an absence: Drive keeps its id and timestamp and
        strips its text and author permanently. So the assertion is not "r1 is gone" - it is
        that r1 has been hollowed out while r2 and the thread's own text are untouched. Those
        three facts together are what distinguishes a targeted delete from a thread delete,
        which would hollow out all three."""
        app = build()
        by_id = {r["id"]: r for r in call(
            app, "delete_comment", commentId="t1", replyId="r1")["replies"]}

        assert by_id["r1"]["content"] is None and by_id["r1"]["author"] is None
        assert by_id["r2"]["content"] == "Second reply", "the sibling reply was taken too"
        assert call(app, "get_comment", commentId="t1")["content"] == "The original point", \
            "the thread's own text was taken too"

    def test_a_reply_that_is_not_on_this_comment_is_refused(self):
        """The dangerous fall-through. A `replyId` that does not match must NOT quietly become
        a thread delete - that is the one mistake here with no way back."""
        app = build()
        with pytest.raises(ToolError) as ei:
            call(app, "delete_comment", commentId="t1", replyId="r-elsewhere")
        assert "r-elsewhere" in str(ei.value)

        still_there = call(app, "get_comment", commentId="t1")
        assert set(replies(still_there)) == {"r1", "r2"}, "a targeted delete widened"

    def test_deleting_the_thread_reports_what_drive_now_holds(self):
        """Read back with `include_deleted=True`. Without it Drive 404s the comment that was
        just deleted, and a successful delete reported "Comment not found"."""
        out = call(build(), "delete_comment", commentId="t1")
        assert out["id"] == "t1"


class TestTheContextLookupIsOptional:
    def test_get_comment_can_ask_for_the_surrounding_text(self):
        """`context=True` is the difference between "Is this accurate?" and knowing what
        "this" was. It is opt-in because it costs a document read.

        `context` is a key in BOTH shapes, carrying None when there is nothing to quote - so
        the test is that asking for it is a supported call that comes back whole, not that
        the key appeared. A key that is always present cannot tell you the flag was honoured."""
        plain = call(build(), "get_comment", commentId="t1")
        with_context = call(build(), "get_comment", commentId="t1", context=True)

        assert "context" in plain and "context" in with_context
        assert with_context["id"] == "t1" and with_context["content"] == "The original point"

    def test_a_doc_export_gathers_the_context_for_every_row_in_one_pass(self):
        """The paired case, and the reason the lookup is a document METHOD rather than a
        per-comment call: a register of two hundred rows would otherwise be two hundred reads
        of the same document."""
        out = call(build(), "export_comments", destination="rows", context=True)
        assert out["rows"]
        assert "context" in out["columns"]

    def test_a_file_type_with_no_context_support_still_lists_its_comments(self):
        """`comment_contexts` lives on `Doc` alone - a spreadsheet has no paragraphs to quote,
        so the attribute is simply absent there. The register has to come back anyway: without
        the context, not without the rows.

        Asking for context on a Sheet is the ordinary case, not a mistake. A caller exporting
        every commented file in a Drive passes one flag for all of them, and a Sheet raising
        `AttributeError` would take down a sweep over a mixed folder."""
        sheet_mime = "application/vnd.google-apps.spreadsheet"
        comments = {"s1": [{"id": "c1", "content": "Check this cell",
                            "author": {"displayName": "A"},
                            "createdTime": "2026-08-20T10:00:00Z",
                            "resolved": False, "replies": []}]}
        backend = FakeBackend({"s1": {"id": "s1", "name": "Book", "mimeType": sheet_mime}},
                              spreadsheets={"s1": {"sheets": [
                                  {"properties": {"title": "Sheet1", "sheetId": 0}}]}},
                              comments=comments)
        st = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*"})
        app = create_server(lambda: Workspace(PolicyBackend(backend, st.policy)), settings=st)

        out = asyncio.run(app.call_tool("export_comments", {
            "fileId": "s1", "destination": "rows", "context": True})).structured_content

        assert out["rows"], "context support is optional; the rows are not"


class TestTheTwoSwitchesAroundTheRegister:
    """`CSA_GW_LOCAL_WRITE` is not a capability. It answers "may this server put review
    material on the disk it is running on?", which is a different question from "may it change
    the document" - and the register workflow crosses it twice, on the way out and on the way
    back."""

    def test_exporting_to_a_file_is_refused_and_says_what_still_works(self):
        """The refusal names the setting, calls it a data-handling setting rather than a
        permission, and points at the destinations that do not touch the disk. Without the
        last part the caller concludes the register is unavailable, when only one delivery
        route is."""
        with pytest.raises(ToolError) as ei:
            call(build(CSA_GW_LOCAL_WRITE="0"), "export_comments", destination="file")
        message = str(ei.value)

        assert "CSA_GW_LOCAL_WRITE" in message
        assert "DATA-HANDLING setting, not a permission" in message

    def test_applying_a_register_that_is_not_a_file_says_what_to_pass(self, tmp_path):
        """A directory, or a path that was never written. The message names `export_comments`
        as the thing that produces a valid one, because the commonest cause is a path typed
        from memory."""
        with pytest.raises(ToolError) as ei:
            call(build(), "apply_comment_actions", path=str(tmp_path), apply=False)
        assert "is not a file" in str(ei.value)
        assert "export_comments" in str(ei.value)

    def test_the_document_still_changes_when_markers_cannot_be_written_back(self, tmp_path):
        """#168's shape, reached the other way. The document has ALREADY been changed by the
        time write-back runs, so a failure there must be reported rather than raised - the
        report is the only surviving record of which rows landed.

        With local write off, the markers cannot be written at all, and the message has to say
        the document WAS updated and that a re-run will repeat the rows. Silence here would
        leave somebody re-running a register that has already been applied, with no way to
        know it."""
        import csv

        from csa_google_workspace import _apply

        register = tmp_path / "r.csv"
        with open(register, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(_apply.COLUMNS))
            writer.writeheader()
            writer.writerow({**{name: "" for name in _apply.COLUMNS},
                             "thread_id": "t1", "resolve_comment": "TRUE"})

        app = build(CSA_GW_LOCAL_WRITE="0")
        out = asyncio.run(app.call_tool("apply_comment_actions", {
            "fileId": DOC, "path": str(register), "apply": True})).structured_content

        assert out["resolved"] == 1, "the document must still have been updated"
        assert "CSA_GW_LOCAL_WRITE is off" in out["detail"]
        assert "re-running is safe but will repeat the rows" in out["detail"]

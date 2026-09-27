"""Every registered tool is callable, described, and declared.

The per-tool suites check behaviour. This checks the thing none of them can: that the *set* is
whole. A tool can be registered and never exercised anywhere, and the failure is silent — it
ships, a model calls it, and it raises. So this walks the registry itself rather than a list
somebody maintained, and a new tool is a test failure until it has smoke arguments here.

It also enforces the three properties every tool needs regardless of what it does:

  * it runs and returns structured output
  * it has a non-empty description — the only interface documentation a model gets, and
    previously missing entirely from one tool because an f-string cannot be a docstring
  * its parameters are camelCase literals — `Field(alias=...)` publishes a correct schema and
    then fails EVERY call, because the SDK dumps by alias and calls fn(**kwargs)
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import tempfile

import pytest

from csa_google_workspace import Workspace, _export
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server

DOC, SHEET, DECK = "doc1", "sheet1", "deck1"
DRIVE = "0ABCDEfakeSharedDrive"

# `authenticate` opens a browser or elicits a URL from the client. Excluded deliberately, and
# named here rather than skipped silently, so "not smoke-tested" stays a visible decision.
INTERACTIVE = {"authenticate"}

# `apply_comment_actions` reads a register off disk, so smoke-testing it needs one to exist.
# A refusal would "pass" a test that only checks the tool runs, which is not the same as the
# tool working - so this writes a real, empty register and the tool walks it with nothing to do.
_REGISTER = pathlib.Path(tempfile.mkdtemp()) / "register.csv"
_REGISTER.write_text(",".join(_export.COLUMNS) + "\n", encoding="utf-8")

ARGS: dict[str, dict] = {
    # Both take no arguments and neither is interactive: `auth_status` makes no call at all,
    # and `whoami` is one `about.get` that `FakeBackend` answers.
    "auth_status":           {},
    "whoami":                {},
    "search_files":          {"query": "Doc"},
    "list_recent_files":     {},
    "get_file_metadata":     {"fileId": DOC},
    "get_file_permissions":  {"fileId": DOC},
    "read_file_content":     {"fileId": DOC},
    "download_file_content": {"fileId": DOC, "exportMimeType": "text/markdown"},
    "list_slides":           {"fileId": DECK},
    "comments_by_cell":      {"fileId": SHEET, "cell": "A1"},
    "list_suggestions":      {"fileId": DOC},
    "list_notes":            {"fileId": SHEET},
    "describe_output_contract": {},
    "list_protected_ranges": {"fileId": SHEET},
    "get_file_restrictions": {"fileId": DOC},
    # A drive id the fixture does not seed, so this exercises the NOT-FOUND path - which is the
    # normal answer for an ordinary user asking about a drive they are not a member of, and the
    # one a smoke test can actually stage.
    "get_shared_drive":      {"driveId": DRIVE},
    "export_comments":       {"fileId": DOC},
    # `query=` rather than `fileIds=`, because the query path is the one a caller
    # reaches for first; the id path is covered in test_work_handoff_inventory.py
    # where the unreachable-reporting it exists for can be asserted.
    "export_file_inventory": {"query": "name contains 'x'"},
    # A DRY RUN over a real but empty register: it reads the file, finds nothing filled in,
    # and reports that. Passing apply=true here would mutate the shared fake mid-suite.
    "apply_comment_actions": {"fileId": DOC, "path": str(_REGISTER)},
    "list_comments":         {"fileId": DOC},
    "create_comment":        {"fileId": DOC, "content": "a comment"},
    "get_comment":           {"fileId": DOC, "commentId": "<made>"},
    "reply_comment":         {"fileId": DOC, "commentId": "<made>", "content": "a reply"},
    "resolve_comment":       {"fileId": DOC, "commentId": "<made>"},
    "reopen_comment":        {"fileId": DOC, "commentId": "<made>"},
    "edit_comment":          {"fileId": DOC, "commentId": "<made>", "content": "edited"},
    "delete_comment":        {"fileId": DOC, "commentId": "<made>"},
    "replace_text":          {"fileId": DOC, "find": "hello", "replace": "goodbye"},
    "append_text":           {"fileId": DOC, "text": "\nmore"},
    "insert_slide_text":     {"fileId": DECK, "objectId": "sh1", "text": "x"},
    "update_cells":          {"fileId": SHEET, "a1Range": "Tab1!A1", "values": [["z"]]},
    "append_rows":           {"fileId": SHEET, "a1Range": "Tab1!A1", "values": [["z"]]},
    "create_file":           {"name": "New", "kind": "document"},
    "copy_file":             {"fileId": DOC, "name": "Copy"},
    "update_file":           {"fileId": DOC, "name": "Renamed"},
    "share_file":            {"fileId": DOC, "emailAddress": "someone@example.com"},
    # `p1` is the permission seeded on DOC in the fixture below. Ordering is load-bearing:
    # update runs first and unshare removes it, so a later reorder that swaps them fails here
    # rather than silently exercising one tool against a missing permission.
    "update_file_permission": {"fileId": DOC, "permissionId": "p1", "role": "reader"},
    "unshare_file":          {"fileId": DOC, "permissionId": "p1"},
    "list_access_proposals": {"fileId": DOC},
    "list_labels":           {"fileId": DOC},
    # DENY rather than approve, so the smoke run does not leave a permission behind that the
    # permission tools above would then see. Both branches are exercised properly in
    # tests/test_access_proposals.py; this asserts the tool is reachable and wired.
    "resolve_access_proposal": {"fileId": DOC, "proposalId": "ap1", "approve": False},
    # last, and deliberately: it trashes the document every earlier tool needs.
    "trash_file":            {"fileId": DOC},
    "describe_configuration": {},
    "preview_allowlist":     {},
    # Tabs and ranges. ORDER IS LOAD-BEARING within each file, as with the permission trio
    # above: add before delete, and never delete the tab a later entry reads.
    "list_tabs":             {"fileId": SHEET},
    "add_tab":               {"fileId": SHEET, "name": "Smoke", "index": 1},
    "delete_tab":            {"fileId": SHEET, "name": "Smoke"},
    "read_range":            {"fileId": SHEET, "a1Range": "Tab1"},
    "clear_cells":           {"fileId": SHEET, "a1Range": "Tab1"},
    "list_document_tabs":    {"fileId": DOC},
    "add_document_tab":      {"fileId": DOC, "title": "Smoke"},
    "delete_document_tab":   {"fileId": DOC, "tabId": "t.fake1"},
    "insert_text":           {"fileId": DOC, "text": "x", "index": 1},
    "delete_range":          {"fileId": DOC, "startIndex": 1, "endIndex": 2},
    "read_server_resource":  {},
    "report_a_problem":      {},
    "demonstration_plan":    {},
}


def _shape() -> dict:
    return {"objectId": "sh1",
            "shape": {"text": {"textElements": [{"textRun": {"content": "slide text"}}]}}}


@pytest.fixture
def server():
    """One backend for the whole run.

    The provider is called per invocation, so a fresh fake each time would discard whatever the
    previous tool created — which made six comment tools look broken when the harness was the
    thing losing state. Against real Google the state lives at Google; a shared instance is the
    faithful model.
    """
    backend = FakeBackend(
        {DOC: {"id": DOC, "name": "A Doc",
               "mimeType": "application/vnd.google-apps.document"},
         SHEET: {"id": SHEET, "name": "A Sheet",
                 "mimeType": "application/vnd.google-apps.spreadsheet"},
         DECK: {"id": DECK, "name": "A Deck",
                "mimeType": "application/vnd.google-apps.presentation"}},
        documents={DOC: {"body": {"content": [
            {"paragraph": {"elements": [{"textRun": {"content": "hello world\n"}}]}}]}}},
        spreadsheets={SHEET: {"sheets": [
            {"properties": {"title": "Tab1", "sheetId": 0},
             # One protected range, so the tool is exercised against a POPULATED answer. A
             # smoke test that only ever saw an empty list would pass while the shaping was
             # broken - the emptiness would be what was under test, not the tool.
             "protectedRanges": [{"protectedRangeId": 1, "description": "locked",
                                  "range": {"sheetId": 0, "startRowIndex": 0,
                                            "endRowIndex": 5}}]}]}},
        values={(SHEET, "Tab1"): [["a", "b"]]},
        presentations={DECK: {"slides": [{"objectId": "s1", "pageElements": [_shape()]}]}},
        drives={DRIVE: {"id": DRIVE, "name": "A Shared Drive",
                        "restrictions": {"driveMembersOnly": True,
                                         "domainUsersOnly": False,
                                         "downloadRestriction": {
                                             "restrictedForReaders": True}}}},
        exports={(DOC, "text/plain"): b"hello world", (DOC, "text/markdown"): b"# hello"},
        permissions={DOC: [{"id": "p1", "type": "user", "role": "writer"}]},
        access_proposals={DOC: [{"proposalId": "ap1", "fileId": DOC,
                                 "requesterEmailAddress": "asker@example.com",
                                 "rolesAndViews": [{"role": "reader"}]}]},
        file_labels={DOC: [{"id": "LBL1", "revisionId": "1",
                            "fields": {"f1": {"valueType": "text", "text": ["x"]}}}]},
        label_definitions={"LBL1": {"id": "LBL1", "properties": {"title": "Sensitivity"},
                                    "fields": [{"id": "f1",
                                                "properties": {"displayName": "Level"}}]}},
    )
    return create_server(lambda: Workspace(backend), settings=settings_from_env(
        {"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
         "CSA_GW_PROFILE": "full"}))


def test_every_tool_has_smoke_arguments(server):
    """A new tool fails here until somebody decides how to exercise it."""
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    undefined = names - set(ARGS) - INTERACTIVE
    assert undefined == set(), (
        f"no smoke arguments for: {sorted(undefined)}. Add them to ARGS, or to INTERACTIVE with "
        f"a reason. A registered tool nothing calls is a tool that ships untested.")


def test_every_tool_runs_and_returns_structured_output(server):
    """The whole set, in one pass, in an order where the comment tools have a comment."""
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    ordered = [n for n in ARGS if n in tools]          # ARGS is ordered: create before use
    made: str | None = None
    failures = []
    for name in ordered:
        args = {k: (made if v == "<made>" else v) for k, v in ARGS[name].items()}
        if any(value is None for value in args.values()):
            failures.append(f"{name}: needed a comment id and none had been created")
            continue
        try:
            result = asyncio.run(server.call_tool(name, args))
        except Exception as error:                     # noqa: BLE001 - report, do not stop
            failures.append(f"{name}: {type(error).__name__}: {error}")
            continue
        if result.structured_content is None:
            failures.append(f"{name}: returned no structured content")
            continue
        if name == "create_comment":
            made = result.structured_content.get("commentId") or \
                   result.structured_content.get("id")
    assert failures == [], "tools failed:\n  " + "\n  ".join(failures)


def test_every_tool_is_described(server):
    """The description is the only interface documentation a model gets.

    One tool once shipped with none, because an f-string was used as a docstring and `__doc__`
    came back None.
    """
    undescribed = [t.name for t in asyncio.run(server.list_tools())
                   if not (t.description or "").strip()]
    assert undescribed == []


def test_parameters_are_camelcase_literals(server):
    """`Field(alias=...)` publishes the right schema and then fails every call.

    The SDK dumps the validated model *by alias* and calls `fn(**kwargs)`, so the handler
    receives `fileId=` for a parameter named `file_id` and raises TypeError — surfacing as an
    UnexpectedToolError with the message suppressed. A camelCase wire name must therefore be
    the literal Python parameter name, which also means no snake_case survives in a schema.
    """
    offenders = []
    for tool in asyncio.run(server.list_tools()):
        for parameter in tool.input_schema.get("properties", {}):
            if "_" in parameter:
                offenders.append(f"{tool.name}.{parameter}")
    assert offenders == [], f"snake_case in a published schema: {offenders}"


def test_comment_descriptions_carry_the_behaviour_that_surprises(server):
    """The comment tools are this project's reason to exist, and were its thinnest docs.

    Each fact below changes how a model should read a result, and none is guessable from the
    tool's name: a deleted comment loses its author as well as its text, resolving posts a
    visible reply rather than setting a flag, and a Sheets anchor cannot be decoded to A1.
    """
    tools = {t.name: (t.description or "") for t in asyncio.run(server.list_tools())}
    assert re.search(r"deleted", tools["list_comments"], re.I)
    assert re.search(r"untrusted", tools["list_comments"], re.I)
    assert re.search(r"repl(y|ies)", tools["resolve_comment"], re.I)
    assert re.search(r"opaque|export", tools["comments_by_cell"], re.I)


def test_a_sheets_comment_can_carry_a_cell_deep_link(server):
    """`cell` was reachable in the library and not through MCP - a differentiator that existed
    and could not be used. It is a LINK, not an anchor: the API cannot anchor a comment to a
    cell at all, which the description says rather than implying otherwise."""
    result = asyncio.run(server.call_tool(
        "create_comment", {"fileId": SHEET, "content": "about B11", "cell": "B11"}))
    assert "range=B11" in result.structured_content["content"]


def test_the_cell_argument_is_ignored_for_documents(server):
    """Docs and Slides have no cells. Passing one is a model's mistake, not a reason to fail."""
    result = asyncio.run(server.call_tool(
        "create_comment", {"fileId": DOC, "content": "plain", "cell": "B11"}))
    assert result.structured_content["content"] == "plain"

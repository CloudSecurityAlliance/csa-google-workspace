"""Which capability each MCP tool can require — so the server stops advertising authority
its tool surface cannot exercise.

The bug this fixes, found by a model that read `describe_configuration`, planned work on the
strength of it, and only then discovered the tools did not exist: the `editor` profile enables
`content.write`, `file.create`, `comment.edit` and `comment.delete`, and **no tool in this
server uses any of them**. They are real policy — a library embedder going through
`Workspace.from_credentials` with that policy genuinely can call `doc.replace_text` — but
reporting them to a model as "enabled" reads as "available", and it is not.

`policy._GATES` answers "what does this *Backend method* cost?". This answers "what can this
*server* actually reach?". Both are needed, because the MCP layer deliberately exposes only
part of the library.

Lives beside `_resources.py` rather than inside `_tools/` because both need it: putting it in
the tools package made `_resources` -> `_tools._capabilities` -> `_tools/__init__` ->
`_tools.config` -> `_resources` a cycle. It is a statement *about* the server, not a tool.

Fail-closed like `_GATES`: `tests/test_mcp_capabilities.py` asserts every registered tool
appears here, so a new tool cannot arrive undeclared and silently widen what the server claims.
"""
from __future__ import annotations

from ..policy import (
    COMMENT_CREATE,
    COMMENT_DELETE,
    COMMENT_EDIT,
    COMMENT_REPLY,
    COMMENT_RESOLVE,
    CONTENT_DELETE,
    CONTENT_WRITE,
    FILE_CREATE,
    FILE_SHARE,
    FILE_TRASH,
    FILE_UPDATE,
)

# Tool name -> the capability a call to it can require, or None for a read.
#
# One entry per registered tool. A read is `None` rather than absent, so a missing key means
# "nobody decided" rather than "it is a read".
TOOL_CAPABILITIES: dict[str, str | None] = {
    # discovery and reads
    "search_files": None,
    "list_recent_files": None,
    "get_file_metadata": None,
    "get_file_permissions": None,
    "read_file_content": None,
    "download_file_content": None,
    "list_comments": None,
    "get_comment": None,
    "comments_by_cell": None,
    # A read, and it stays a read: accept/reject would need a capability, and the Docs API
    # has no endpoint for either, so there is nothing to gate.
    "list_suggestions": None,
    "list_notes": None,                # a read; notes are read-only in this library
    # All three are reads, and read-only by CONSTRUCTION rather than by configuration: there is
    # no write counterpart anywhere in the library, and no capability that would enable one.
    # These are the controls that bound every client, so an agent able to lift one has not
    # been restricted (#336, #337, #338).
    "list_protected_ranges": None,
    "get_file_restrictions": None,
    "get_shared_drive": None,
    # A read of THIS SERVER'S OWN SHAPE - no Google call at all, so not even a file is
    # touched. It exists so a consumer can stop diffing payloads to learn the contract.
    "describe_output_contract": None,
    "export_comments": None,
    # Also `None`, for the same reason and with the same lossiness: reading is ungated,
    # but destination="sheet" creates a Drive file and so needs `file.create`. A
    # one-capability-per-tool map cannot say "depends on the argument" - see
    # tests/test_mcp_capabilities.py::test_the_reverse_is_deliberately_not_asserted.
    "export_file_inventory": None,
    # Declares comment.reply; resolving is gated independently at the Backend wrapper, so
    # an operator who granted only one of the two gets exactly that one - the tool cannot
    # smuggle the other through. Declared rather than left None because it is a WRITE.
    "apply_comment_actions": COMMENT_REPLY,
    # comment writes
    "create_comment": COMMENT_CREATE,
    "reply_comment": COMMENT_REPLY,
    "resolve_comment": COMMENT_RESOLVE,
    "reopen_comment": COMMENT_RESOLVE,
    "edit_comment": COMMENT_EDIT,
    "delete_comment": COMMENT_DELETE,
    # content writes
    "replace_text": CONTENT_WRITE,
    "append_text": CONTENT_WRITE,
    "update_cells": CONTENT_WRITE,
    "append_rows": CONTENT_WRITE,
    "list_slides": None,
    "insert_slide_text": CONTENT_WRITE,
    # creation
    "create_file": FILE_CREATE,
    "copy_file": FILE_CREATE,
    # file lifecycle - each maps to the capability that gates it, so
    # `capabilities_unreachable` becomes empty for the `full` profile: every capability the
    # policy can grant now has a tool that uses it.
    "update_file": FILE_UPDATE,
    "trash_file": FILE_TRASH,
    "share_file": FILE_SHARE,
    # Ungranting is the same authority as granting - an operator who may hand out
    # access may take it back. See policy._GATES.
    "update_file_permission": FILE_SHARE,
    "unshare_file": FILE_SHARE,
    # Answering an access request. `resolve_access_proposal` is `share_file` under another
    # name - approving it grants a real permission - so it costs the same capability, and it
    # costs it for a DENIAL too: an operator who turned `file.share` off said this server does
    # not decide who gets access, and "no" is still deciding. See policy._GATES.
    "resolve_access_proposal": FILE_SHARE,
    # "Who is waiting?" has no write in it.
    "list_access_proposals": None,
    # A read, and one this server can ONLY do: it never requests the write scope
    # for labels, so there is no capability that would enable relabelling.
    "list_labels": None,
    # Reads the policy this server already holds and resolves the ids in it.
    "preview_allowlist": None,
    # Tabs and the ranges. Reads are ungated; adding is a content write; DELETING is its own
    # capability, because it takes the content with it and there is no trash and no API undo.
    "list_tabs": None,
    "list_document_tabs": None,
    "read_range": None,
    "add_tab": CONTENT_WRITE,
    "add_document_tab": CONTENT_WRITE,
    "insert_text": CONTENT_WRITE,
    "delete_tab": CONTENT_DELETE,
    "delete_document_tab": CONTENT_DELETE,
    "delete_range": CONTENT_DELETE,
    # CONTENT_WRITE, matching `policy._GATES`. This said CONTENT_DELETE and was the ORIGIN
    # of the F1 inconsistency (audit 2026-09-01-02): being hand-written, it disagreed with
    # the gate and then propagated - `demonstration_plan` predicted a refusal that would
    # not happen, and the tool description told a model the wrong capability. Blanking
    # cells is `content.write` deliberately; see the note on CONTENT_WRITE in policy.py.
    "clear_cells": CONTENT_WRITE,
    # about the server rather than about Google; no Google call, so no capability
    "describe_configuration": None,
    # A read in the strict sense - it touches no Google API at all, only this process.
    "report_a_problem": None,
    # Returns a plan; carrying it out is the model calling the tools it names,
    # each of which is gated on its own.
    "demonstration_plan": None,
    "read_server_resource": None,
    "authenticate": None,
    # No Google call at all - only this process's own view of a local token file.
    "auth_status": None,
    # One `about.get` against the caller's OWN account. `None` like every other read here:
    # capabilities in this server gate WRITES, and reads are bounded by the granted scope.
    "whoami": None,
}


def reachable_capabilities() -> frozenset[str]:
    """Capabilities some tool in this server can actually require."""
    return frozenset(c for c in TOOL_CAPABILITIES.values() if c is not None)

"""The matrix: every operation, against every file type that supports it.

Not "call each tool once". A comment behaves the same on a Doc, a Sheet and a deck because
comments are a uniform Drive concern — but *content* is three different APIs, and the seam
between the two is where this library's bugs have actually lived. So the plan is a product:
each file type crossed with the full operation set, and the type-specific content operations
attached to the type that has them.

**Add, edit, remove** is spelled out per type rather than assumed, because "edit text" means
`replace_text` on a Doc, `update_cells` on a Sheet and a shape-addressed `replace_text` on a
deck, and only one of those three resembles the others.

Steps are data, not code, for two reasons. A narrated demo and an unattended test are then the
same list read at two speeds — one prints `narrate` and pauses, the other does not. And the
coverage report can be computed from the plan before anything runs, so "which tools does this
exercise?" is answerable without a Google account.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from ..mcp._capabilities import TOOL_CAPABILITIES

# What each file type is called, what its content operations are, and how to seed it. Keyed by
# the `kind` that `create_file` takes.
TYPES = ("document", "spreadsheet", "presentation")

State = dict[str, Any]


@dataclass(frozen=True)
class Step:
    """One tool call, with everything a narrator or a report needs to describe it."""

    tool: str
    # `Callable[..., ]` rather than `Callable[[State], ]`: the steps bind loop variables
    # through default arguments (`lambda s, key=key: ...`), which is the plain way to write
    # a table of closures and does not match the one-argument signature.
    args: Callable[..., dict[str, Any]]
    narrate: str                       # what is happening, in a sentence
    teaches: str = ""                  # why it is worth knowing; shown when stepping through
    captures: Callable[..., None] | None = None   # thread ids to later steps
    requires: str | None = None        # capability; the step is skipped if it is off
    optional: bool = False             # a failure here is reported, not fatal
    group: str = ""                    # for the report: which file type, or "account"


def _require_share(state: State) -> str:
    """The address to share with, or a KeyError the runner turns into a clean skip."""
    address = state.get("share_with")
    if not address:
        raise KeyError("no address to share with; pass --share EMAIL")
    return str(address)


def _folder(state: State) -> dict:
    return {"parentId": state["folder_id"]} if state.get("folder_id") else {}


def account_opening() -> list[Step]:
    """Before any file exists: what the server is, and where the work will go."""
    return [
        Step("demonstration_plan", lambda s: {},
             "Ask the server for the plan we are about to follow",
             "The same list a model gets when somebody asks for a demonstration - it reports "
             "what the current policy will refuse, so a walkthrough can say up front what it "
             "will have to skip rather than hitting the refusal halfway through.",
             group="account"),
        Step("auth_status", lambda s: {},
             "Ask whether this server is logged in, without calling Google",
             "No network call at all - it reads the local token file and reports one of three "
             "states. `scope_short` is the one worth knowing: a credential that IS valid and "
             "just predates a scope this deployment now needs, which is a re-consent rather "
             "than a first login. It also names the Google Cloud project the OAuth client "
             "belongs to, which is the only way to tell which side of a project migration a "
             "token is on.",
             group="account"),
        Step("whoami", lambda s: {},
             "Ask which Google account the server is acting as",
             "One narrow `about.get`; it reads no files. Worth doing before any write, because "
             "this server can hold sharing and trashing rights over every file the credential "
             "reaches - a wrong-account token should be caught before it acts, not after.",
             group="account"),
        Step("describe_configuration", lambda s: {},
             "Ask the server what it is allowed to do",
             "Every refusal later is explained by this. It reports the version, the OS, which "
             "capabilities are on, and which files are in scope - and none of it can be "
             "changed from inside a conversation.",
             group="account"),
        Step("create_file", lambda s: {"name": s["folder_name"], "kind": "folder"},
             "Create a folder to keep the demonstration in",
             "Everything below lands here, so the whole run can be found - and removed - in "
             "one place.",
             captures=lambda s, out: s.update(folder_id=out["id"], folder_url=out.get("url")),
             group="account"),
    ]


def per_type(kind: str) -> list[Step]:
    """The full operation set for one file type."""
    key = f"{kind}_id"
    label = {"document": "Doc", "spreadsheet": "Sheet", "presentation": "deck"}[kind]

    steps: list[Step] = [
        Step("create_file",
             lambda s, k=kind: {"name": f"{s['prefix']} {k}", "kind": k, **_folder(s)},
             f"Create a {label}",
             "One tool, three file types: `kind` decides which. The id it returns is what "
             "every later call uses.",
             captures=lambda s, out, key=key: s.update({key: out["id"],
                                                        f"{key}_url": out.get("url")}),
             group=kind),
        Step("describe_output_contract", lambda s: {},
             "Ask the server what SHAPE its answers take",
             "The vocabularies are OPEN and gain members - `spanning` arrived in 0.48.0 - so a "
             "consumer that treats them as closed breaks on upgrade. This is that contract, "
             "readable at runtime instead of diffed between two payloads.", group=kind),
        Step("get_file_metadata", lambda s, key=key: {"fileId": s[key]},
             f"Read the {label}'s metadata",
             "Name, type, and when it changed - without fetching the content, which for a "
             "large file is the difference between instant and slow.",
             group=kind),
        Step("get_file_restrictions", lambda s, key=key: {"fileId": s[key]},
             f"Ask what DRIVE permits on the {label}",
             "Two questions in one answer: the configured restriction flags, and what Drive "
             "will actually permit THIS user once the flags, the sharing and any shared-drive "
             "policy are all applied. A model deciding whether to attempt something wants the "
             "second - `can_share=false` means Google will refuse however this server is set "
             "up, so trying it wastes a turn on a predictable failure.",
             group=kind),
    ]

    # ── Content: add, edit, remove — spelled out per type, because they are three APIs ──
    if kind == "document":
        steps += [
            Step("append_text", lambda s: {"fileId": s["document_id"],
                                           "text": "\nAdded by the demonstration.\n"},
                 "Add text to the Doc",
                 "Appends to the body exactly as given - including your own newline, if you "
                 "want a new paragraph.", group=kind),
            Step("replace_text", lambda s: {"fileId": s["document_id"],
                                            "find": "Added", "replace": "Edited"},
                 "Edit that text",
                 "Document-wide find and replace, and it reports how many occurrences it "
                 "changed - which is how you notice a find that matched more than you meant.",
                 group=kind),
            Step("insert_text", lambda s: {"fileId": s["document_id"],
                                           "text": "Inserted at the top. ", "index": 1},
                 "Insert text at a POSITION",
                 "Not the same as appending: `index` is a Docs character offset, and 1 is the "
                 "start of the body because 0 is the document itself. Position matters when "
                 "you are building a document rather than adding to one.", group=kind),
            Step("delete_range", lambda s: {"fileId": s["document_id"],
                                            "startIndex": 1, "endIndex": 22},
                 "Delete a span of text outright",
                 "This narration used to say 'there is no separate delete tool, because there "
                 "is no separate Google API'. Both halves were wrong: `deleteContentRange` is "
                 "its own request, and this is its own tool - gated by `content.delete` rather "
                 "than `content.write`, because destroying content is not editing it and an "
                 "operator may permit one and refuse the other.", group=kind),
            Step("list_document_tabs", lambda s: {"fileId": s["document_id"]},
                 "List the Doc's TABS",
                 "Google Docs have tabs, and they nest. Expect one here. Reading only the "
                 "first tab was a real bug (#280): a two-tab document reported as a one-tab "
                 "document, silently.", group=kind),
            Step("add_document_tab", lambda s: {"fileId": s["document_id"], "title": "Appendix"},
                 "Add a second tab",
                 "Google auto-titles a tab if you do not. Note tabs are addressed by ID, never "
                 "by title - a Doc may legitimately have two tabs with the same name, unlike a "
                 "spreadsheet.",
                 captures=lambda s, out: s.__setitem__(
                     "doc_tab_id",
                     next((tab["tab_id"] for tab in out["tabs"]
                           if tab["title"] == "Appendix"), None)),
                 group=kind),
            Step("read_file_content", lambda s: {"fileId": s["document_id"]},
                 "Read the Doc again, now that it has two tabs",
                 "THIS IS THE REGRESSION TEST FOR #280, run against real Google. Both tabs "
                 "must appear, each headed `# <tab>`. Before the fix this returned tab 1 only "
                 "and said nothing about the rest.", group=kind),
            Step("delete_document_tab", lambda s: {"fileId": s["document_id"],
                                                   "tabId": s.get("doc_tab_id")},
                 "Delete that tab again",
                 "By id, because titles are not unique. Everything in the tab goes with it - "
                 "no trash, no undo through the API - which is why this is `content.delete`.",
                 group=kind),
            Step("list_suggestions", lambda s: {"fileId": s["document_id"]},
                 "Look for tracked-change suggestions",
                 "Empty here, because a suggestion can only be MADE in the editor - which is "
                 "the point worth seeing: this reads them and previews what they would do, "
                 "and nothing can accept or reject one, because the Docs API has no endpoint "
                 "for either.", group=kind),
        ]
    elif kind == "spreadsheet":
        steps += [
            Step("list_protected_ranges", lambda s: {"fileId": s["spreadsheet_id"]},
                 "Ask what GOOGLE will refuse to let us edit",
                 "A protected range is enforced by Google against every client, so it is a "
                 "categorically stronger answer than this server's own policy - which binds "
                 "only this server's calls. Expect zero here: the demo just made this file, so "
                 "nothing is protected yet. Zero is the useful answer, not a failure.",
                 group=kind),
            Step("list_notes", lambda s: {"fileId": s["spreadsheet_id"]},
                 "List the cell NOTES on the Sheet",
                 "Notes are NOT comments - no author, no thread, and they cannot be replied to "
                 "or resolved. `list_comments` does not show them, so a survey that asks only "
                 "for comments reports a sheet covered in notes as having none.", group=kind),
            Step("update_cells", lambda s: {"fileId": s["spreadsheet_id"], "a1Range": "A1:B2",
                                            "values": [["Item", "Count"], ["Widgets", "7"]]},
                 "Write cells into the Sheet",
                 "A1 notation, and the values go in as typed unless you ask Google to parse "
                 "them.", group=kind),
            Step("append_rows", lambda s: {"fileId": s["spreadsheet_id"], "a1Range": "A1",
                                           "values": [["Sprockets", "3"]]},
                 "Append a row",
                 "Appending finds the end of the data for itself, so it does not overwrite "
                 "the row you forgot about.", group=kind),
            Step("read_range", lambda s: {"fileId": s["spreadsheet_id"], "a1Range": "A1:B3"},
                 "Read ONE range back",
                 "Cheaper and more precise than `read_file_content`, which renders every tab "
                 "of the workbook as text. Use it when you know where you are looking.",
                 group=kind),
            Step("list_tabs", lambda s: {"fileId": s["spreadsheet_id"]},
                 "List the Sheet's tabs",
                 "Watch `hidden`: a hidden tab still exists, still holds data, and still "
                 "occupies its name - so `add_tab` can be refused by a tab nobody can see.",
                 group=kind),
            Step("add_tab", lambda s: {"fileId": s["spreadsheet_id"], "name": "Title",
                                       "index": 0},
                 "Add a tab, first in the order",
                 "`index=0` because a spreadsheet opens on its first tab, which is the whole "
                 "reason a register wants a title tab. Adding a name that already exists is "
                 "REFUSED rather than silently renamed to 'Title 2' - a caller re-running a "
                 "build needs 'already there' told apart from 'created'.", group=kind),
            Step("update_cells", lambda s: {"fileId": s["spreadsheet_id"],
                                            "a1Range": "Title!A1:A2",
                                            "values": [["Review register"],
                                                       ["Generated by the demonstration"]]},
                 "Write into the tab by name",
                 "This is what needed `add_tab` to exist: writing to `Title!A1` fails with "
                 "'Unable to parse range' if no such tab is there, and the error does not say "
                 "that is why.", group=kind),
            Step("clear_cells", lambda s: {"fileId": s["spreadsheet_id"],
                                           "a1Range": "Title!A1:A2"},
                 "CLEAR those cells - not overwrite them",
                 "This narration used to say 'clearing is writing empty values, same tool, no "
                 "separate delete'. It was wrong: writing `\"\"` leaves cells CONTAINING an "
                 "empty string, which anything reading the sheet can tell apart from an empty "
                 "cell. `content.delete`, for the same reason as the Doc delete.", group=kind),
            Step("delete_tab", lambda s: {"fileId": s["spreadsheet_id"], "name": "Title"},
                 "Delete the tab",
                 "Every cell in it goes too. Google refuses to delete the only tab in a "
                 "spreadsheet, and so does this.", group=kind),
        ]
    else:
        steps += [
            Step("list_slides", lambda s: {"fileId": s["presentation_id"]},
                 "List the slides and their shapes",
                 "Slides content is addressed by SHAPE, not by position in a document - so "
                 "this is the step that tells you what you are allowed to write into.",
                 captures=lambda s, out: s.update(
                     shape_id=next((sid for slide in out.get("slides", [])
                                    for sid in slide.get("shape_ids", [])), None)),
                 group=kind),
            Step("insert_slide_text",
                 lambda s: {"fileId": s["presentation_id"], "objectId": s["shape_id"],
                            "text": "Added by the demonstration"},
                 "Add text into a shape",
                 "The objectId comes from the step above. There is no 'append to the deck' - "
                 "text belongs to a shape.", optional=True, group=kind),
            Step("replace_text", lambda s: {"fileId": s["presentation_id"],
                                            "find": "Added", "replace": "Edited"},
                 "Edit that text across the deck",
                 "Deck-wide, unlike insert: useful for a term that appears on every slide.",
                 optional=True, group=kind),
            Step("replace_text", lambda s: {"fileId": s["presentation_id"],
                                            "find": "Edited by the demonstration",
                                            "replace": ""},
                 "Remove it again", "Same shape as the Doc: replace with nothing.",
                 optional=True, group=kind),
        ]

    steps.append(
        Step("read_file_content", lambda s, key=key: {"fileId": s[key]},
             f"Read the {label} back as text",
             "One tool for all three types, which is the point: the caller does not have to "
             "know which Google API produced the text.", group=kind))

    # ── Comments: identical across types, which is exactly why all three are exercised ──
    steps += [
        Step("create_comment",
             lambda s, key=key, k=kind: {"fileId": s[key],
                                         "content": f"Demonstration comment on the {k}.",
                                         **({"cell": "A1"} if k == "spreadsheet" else {})},
             f"Comment on the {label}",
             "On a Sheet this also takes `cell`, which appends a deep link - a link, not a "
             "true anchor, because the Drive API cannot anchor a comment to a cell at all.",
             captures=lambda s, out: s.update(comment_id=out.get("commentId") or out.get("id")),
             group=kind),
        Step("list_comments", lambda s, key=key: {"fileId": s[key]},
             "List the comments", "Newest thread first, replies included.", group=kind),
        Step("get_comment", lambda s, key=key: {"fileId": s[key],
                                                "commentId": s["comment_id"]},
             "Read that one thread", "Including the action replies Google writes when a "
             "thread is resolved or reopened.", group=kind),
        Step("reply_comment", lambda s, key=key: {"fileId": s[key],
                                                  "commentId": s["comment_id"],
                                                  "content": "A reply."},
             "Reply to it", "Replying does not resolve - the two are separate acts.",
             group=kind),
        Step("edit_comment", lambda s, key=key: {"fileId": s[key],
                                                 "commentId": s["comment_id"],
                                                 "content": "An edited comment."},
             "Edit the comment",
             "Google keeps no visible edit history, so the previous text is gone - quote it "
             "back to somebody if they might want it.", group=kind),
        Step("resolve_comment", lambda s, key=key: {"fileId": s[key],
                                                    "commentId": s["comment_id"],
                                                    "content": "Resolving in the demo."},
             "Resolve the thread",
             "This posts a VISIBLE reply under your name. It is not a silent flag, which is "
             "why the closing note matters.", group=kind),
        Step("reopen_comment", lambda s, key=key: {"fileId": s[key],
                                                   "commentId": s["comment_id"]},
             "Reopen it", "Also a visible reply. Resolving is reversible.", group=kind),
        Step("delete_comment", lambda s, key=key: {"fileId": s[key],
                                                   "commentId": s["comment_id"]},
             "Delete the comment",
             "A soft delete: the thread keeps its place and its id, and loses BOTH its text "
             "and its author. Not 'author unknown' - the record is gone.", group=kind),
    ]

    # Every type, because the whole point is that one call covers a file whatever it is - and
    # the column that makes it useful differs per type, which is worth seeing three times.
    steps += [
        Step("export_comments", lambda s, key=key: {"fileId": s[key]},
             f"Export every comment on the {label} as rows",
             "One call for a whole file: flat rows with ordered columns, the shape you write to "
             "a spreadsheet or hand to another tool. For a Doc the useful column is the passage "
             "each comment is about; for a Sheet it is what the CELL holds.", group=kind),
        # Written to disk so the NEXT step has something real to read. The round trip is the
        # demonstration: a register is only useful if it can come back.
        Step("export_comments",
             lambda s, key=key: {"fileId": s[key], "destination": "file"},
             f"Write that register out as a .csv ({label})",
             "destination=\"file\" puts it in your Downloads folder and returns the path; "
             "\"xlsx\" gives a formatted workbook, and \"sheet\" a Google Sheet you can share. "
             "Only destination=\"rows\" returns the rows themselves - a file destination that "
             "also echoed the payload broke on a 205-comment document.",
             captures=lambda s, out: s.update(register=out.get("written_path")),
             optional=True, group=kind),
        Step("apply_comment_actions",
             # key=key, as every other step in per_type() does. Without it this resolved
             # `document_id or spreadsheet_id or presentation_id`, and document_id is populated
             # first - so the spreadsheet and presentation groups applied THEIR register to the
             # Doc, and passed green because a demo register has nothing filled in. (#165)
             lambda s, key=key: {"fileId": s[key], "path": s["register"]},
             f"Show what applying that register back would do ({label})",
             "The other half of the export: fill in reply_comment and resolve_comment in the "
             "spreadsheet, hand it back, and it posts the replies and resolves the threads. "
             "NOTHING happens without apply=true - this is the dry run. It is also safe to "
             "re-run: it checks the document itself, not just its own tick-boxes, so a run "
             "interrupted half way cannot post the same reply twice. Nothing is filled in "
             "here, so it reports nothing to do.",
             optional=True, group=kind),
    ]

    if kind == "spreadsheet":
        steps.append(
            Step("comments_by_cell", lambda s: {"fileId": s["spreadsheet_id"], "cell": "A1"},
                 "Ask which comments are about cell A1",
                 "Recovering this means exporting the file as XLSX and reading the anchors "
                 "out of it, because Drive reports a spreadsheet anchor as an opaque id. "
                 "Best-effort by construction.", optional=True, group=kind))

    steps += [
        Step("download_file_content",
             lambda s, key=key, k=kind: {
                 "fileId": s[key],
                 "exportMimeType": {"document": "text/markdown",
                                    "spreadsheet": "text/csv",
                                    "presentation": "text/plain"}[k]},
             f"Export the {label}",
             "Markdown out of a Doc is what makes this composable with a document pipeline; "
             "CSV out of a Sheet is what makes it composable with everything else.",
             group=kind),
        Step("get_file_permissions", lambda s, key=key: {"fileId": s[key]},
             "See who can reach it",
             "Reading who has access is ungated. GRANTING access is not - see the next step.",
             group=kind),
        Step("list_labels", lambda s, key=key: {"fileId": s[key]},
             "See how it is CLASSIFIED",
             "Drive labels, resolved to names through a second API. Expect zero on a file this "
             "demo just made. Watch the distinction: `labelled: false` means no labels, while "
             "`labelled: true` with `names_unavailable: true` means labels exist and could not "
             "be NAMED - never the same answer.",
             group=kind),
        Step("list_access_proposals", lambda s, key=key: {"fileId": s[key]},
             "See who has ASKED to reach it",
             "The other side of access: people who hit the file without permission and "
             "requested it. Expect zero here - a proposal needs a different human, with no "
             "access, to click 'Request access', which no API can do. Zero is the answer, not "
             "a failure. Note what the tool does NOT do: there is no way to request access, "
             "only to answer requests.",
             group=kind),
        Step("copy_file", lambda s, key=key, k=kind: {"fileId": s[key],
                                                      "name": f"{s['prefix']} {k} (copy)",
                                                      **_folder(s)},
             f"Copy the {label}",
             "The copy is a NEW id, so it is not covered by a modify allowlist that named the "
             "original. Copying cannot be used to obtain a writable duplicate.",
             captures=lambda s, out, k=kind: s.setdefault("copies", []).append(out["id"]),
             group=kind),
        Step("update_file", lambda s, key=key, k=kind: {"fileId": s[key],
                                                        "name": f"{s['prefix']} {k} (renamed)"},
             f"Rename the {label}",
             "Metadata only. Renaming is not editing - content is a different API per type.",
             requires="file.update", group=kind),
        # Skipped rather than failed when there is no address to share with: the first real
        # run passed an empty string and got "expected an email address", which reads as a
        # broken tool rather than as a missing option.
        Step("share_file", lambda s, key=key: {"fileId": s[key],
                                               "emailAddress": _require_share(s),
                                               "role": "reader",
                                               "sendNotification": True},
             "Share it",
             "The only step here that can move data OUT of the organisation, and it is ON BY "
             "DEFAULT, so this step is reachable on an unconfigured install. The recipient IS "
             "notified - a grant somebody is told about is one they can question, which is "
             "exactly why it should not be quiet in a demonstration either.",
             captures=lambda s, out, k=kind: s.update({f"perm_{k}": out.get("id")}),
             requires="file.share", optional=True, group=kind),
        # Paired with the share above, deliberately: a demonstration that grants access and
        # cannot take it back leaves the reviewer's Drive changed. These put it back.
        #
        # The permission id comes from `share_file`'s own result via `captures`, not from a
        # guess - it is Google's to choose, and against real Drive a hard-coded one would be
        # wrong on every run.
        Step("update_file_permission",
             lambda s, key=key, k=kind: {"fileId": s[key],
                                         "permissionId": s.get(f"perm_{k}", ""),
                                         "role": "commenter"},
             "Downgrade that share",
             "Often what is actually wanted: the person keeps seeing the document and stops "
             "being able to change it, rather than losing access mid-task.",
             requires="file.share", optional=True, group=kind),
        Step("unshare_file",
             lambda s, key=key, k=kind: {"fileId": s[key],
                                         "permissionId": s.get(f"perm_{k}", "")},
             "Revoke it again",
             "The grant is gone, so the demo leaves nothing behind. Worth noticing what it "
             "does NOT do: a copy the recipient already took is not recalled, and Drive sends "
             "no notification - 'revoked' means less than it sounds.",
             requires="file.share", optional=True, group=kind),
    ]
    return steps



def account_closing() -> list[Step]:
    """After the files exist: the account-wide tools, which need something to find."""
    return [
        Step("search_files",
             lambda s: {"query": f"name contains '{s['prefix']}'", "limit": 10},
             "Search for what was just created",
             "Drive's own query syntax, not free text - `name contains '...'` rather than the "
             "words alone. Passing the words alone is a 400 from Google, which is exactly what "
             "the first run of this demonstration did.", group="account"),
        Step("list_recent_files", lambda s: {"limit": 5},
             "List recently touched files",
             "What a person means by 'the thing I was just working on'.", group="account"),
        Step("export_file_inventory",
             lambda s: {"query": f"name contains '{s['prefix']}'", "subject": s.get("whoami"),
                        "limit": 10},
             "Take a dated inventory of one person's work",
             "The work-handoff question: somebody is away for a month and something arrives "
             "that cannot wait. One table of every file they edited or commented on, with "
             "empty columns for your own summary and tags. Note that `unreachable` is part of "
             "the answer - this runs as you, so ids you cannot read are reported with a reason "
             "rather than dropped, because a table of only the readable files reads as a "
             "complete footprint.", group="account"),
        Step("read_server_resource", lambda s: {},
             "Read the server's own documentation",
             "Published as an MCP resource, and also as a tool - because several clients "
             "surface resources only to the user, never to the model.", group="account"),
        Step("report_a_problem", lambda s: {},
             "Assemble a bug report",
             "Version, OS, Python, install route and the active policy - with no file ids, "
             "titles or paths, so it is safe to paste into a public tracker.",
             captures=lambda s, out: s.update(problem_report=out.get("report")),
             group="account"),
    ]


def cleanup(keep: bool) -> list[Step]:
    """Trash what was made. Runs even when steps failed, unless `keep`."""
    if keep:
        return []

    def targets(state: State) -> list[str]:
        """Everything made, children before the folder that holds them."""
        ids = [state.get(f"{kind}_id") for kind in TYPES]
        return [i for i in ids + list(state.get("copies", [])) + [state.get("folder_id")] if i]

    # Demonstrate that trashing is reversible on ONE file, then actually clear up. The first
    # version stopped after the demonstration and left the whole folder behind - which is not
    # cleanup, it is a demo of cleanup, and the difference is somebody else's Drive.
    steps = [
        Step("trash_file", lambda s: {"fileId": targets(s)[0]},
             "Trash a file, to show what that does",
             "Trashing is recoverable for 30 days, and the same tool restores it. There is no "
             "permanent delete in this library at all.", requires="file.trash", optional=True,
             group="cleanup"),
        Step("trash_file", lambda s: {"fileId": targets(s)[0], "untrash": True},
             "Restore it, to show that trashing is reversible", "",
             requires="file.trash", optional=True, group="cleanup"),
    ]
    # Then everything, folder last: trashing a folder does not trash what is inside it, so the
    # children have to go first or they are left loose in My Drive.
    for index in range(_MAX_CLEANUP):
        steps.append(Step(
            "trash_file",
            lambda s, i=index: {"fileId": targets(s)[i]},
            "Tidy up",
            "", requires="file.trash", optional=True, group="cleanup"))
    return steps


# Enough for three files, three copies and the folder, with room to spare. A fixed count
# rather than a loop over state, because the plan is built before anything has run - which is
# what lets the coverage report be computed without a Google account. Steps that find nothing
# to trash skip themselves.
_MAX_CLEANUP = 8


def build(prefix: str, folder_name: str, share_with: str, *, keep: bool) -> list[Step]:
    """The whole plan, in the order a person would meet it, every gated step annotated."""
    steps = account_opening()
    for kind in TYPES:
        steps += per_type(kind)
    steps += account_closing()
    steps += cleanup(keep)
    return [_annotate(step) for step in steps]


def _annotate(step: Step) -> Step:
    """Fill in `requires` from the server's own tool->capability map.

    Steps used to declare `requires` **only** for capabilities that were off by default, which
    worked by accident: everything else was always on, so an unannotated step never met a
    refusal. Two things broke that. A `reader` or `commenter` profile already walked into
    refusals the plan could have predicted, and v0.21.0 moved `comment.edit` and
    `comment.delete` out of the default - so the most common configuration started hitting
    them. `demonstration_plan` exists precisely to say up front what will be skipped, and it
    could not.

    Derived rather than hand-annotated because 22 of the 36 steps are gated and a table
    somebody has to remember is a table that goes stale. `TOOL_CAPABILITIES` is already the
    single source of truth - `tests/test_mcp_capabilities.py` fails if a tool is missing from
    it - so reading it here means a new gated tool arrives correctly annotated for free. An
    explicit `requires=` still wins, for the one case the map cannot express: `resolve_comment`
    and `reopen_comment` share a capability, and a step may need a NARROWER one than its tool.
    """
    if step.requires is not None:
        return step
    capability = TOOL_CAPABILITIES.get(step.tool)
    return replace(step, requires=capability) if capability else step


def initial_state(prefix: str, folder_name: str, share_with: str) -> State:
    return {"prefix": prefix, "folder_name": folder_name, "share_with": share_with,
            "copies": []}


@dataclass
class Outcome:
    """What happened to one step."""
    step: Step
    status: str                      # ok | skipped | failed
    detail: str = ""
    result: Any = None
    seconds: float = 0.0


@dataclass
class Report:
    outcomes: list[Outcome] = field(default_factory=list)
    state: State = field(default_factory=dict)

    @property
    def ok(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "ok")

    @property
    def failed(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.status == "failed"]

    @property
    def skipped(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.status == "skipped"]

    def tools_exercised(self) -> set[str]:
        return {o.step.tool for o in self.outcomes if o.status == "ok"}

#!/usr/bin/env python3
"""Build the public specimen corpus — idempotently, so it can be re-run.

`CSA-CINO-Public-Artifacts / google-workspace-api-specimens / comments`

**The file's content IS its documentation.** Each specimen explains what it is, which measured
finding it evidences, what to look at, and what a human still has to place by hand — so it works
as documentation the moment somebody opens the link, and it cannot drift from the fixture it
describes, because it *is* the fixture.

## What this script can and cannot do

It creates the files, writes their self-describing content, and places the comments **only the
API can make**: file-level, and quote-only (a quote with no anchor). Everything else needs a
human in a browser, because the editor is the only thing that mints a real anchor — an
API-supplied one is stored verbatim and then ignored. Each file lists its own outstanding
hand-placement under "STILL TO BE PLACED BY HAND", so the instructions travel with the
specimen rather than living in a script nobody reads twice.

## Idempotent on purpose

Re-running must not produce `docs-anchor-states (2)`. Files are matched by name within the
folder and reused; content is rewritten only with `--rewrite`, because a rewrite shifts every
character index and therefore breaks every hand-placed anchor on that file. That is the one
destructive thing in here and it is opt-in.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from _content import HEADINGS, README, SPECIMENS, body  # noqa: E402  # sibling
from googleapiclient.discovery import build  # noqa: E402
from googleapiclient.errors import HttpError  # noqa: E402

from csa_google_workspace.auth import load_cached_credentials  # noqa: E402

TODAY = _dt.date.today().isoformat()
TOKEN = os.environ.get("CSA_GW_TOKEN", "~/.csa_google_workspace/token.json")
DRIVE_NAME = "CSA-CINO-Public-Artifacts"
TOP = "google-workspace-api-specimens"
SUB = "comments"
FOLDER = "application/vnd.google-apps.folder"
DOC = "application/vnd.google-apps.document"


def services():
    creds = load_cached_credentials(TOKEN, read_only=False)
    return (build("drive", "v3", credentials=creds),
            build("docs", "v1", credentials=creds))


def find_drive(drive) -> str:
    page = None
    while True:
        got = drive.drives().list(pageSize=100, pageToken=page,
                                  fields="nextPageToken,drives(id,name)").execute()
        for d in got.get("drives", []):
            if d["name"] == DRIVE_NAME:
                return d["id"]
        page = got.get("nextPageToken")
        if not page:
            raise SystemExit(f"no shared drive named {DRIVE_NAME!r}")


def find_or_make(drive, name: str, parent: str, drive_id: str, mime: str) -> tuple[str, bool]:
    """`(id, created)`. Matched by NAME within the parent, so a re-run reuses rather than
    duplicating — `docs-anchor-states (2)` would be worse than no specimen at all, because a
    manifest citing one id while a reader opens the other is a silent disagreement."""
    q = (f"name = '{name}' and mimeType = '{mime}' and '{parent}' in parents "
         f"and trashed = false")
    hit = drive.files().list(q=q, corpora="drive", driveId=drive_id,
                             includeItemsFromAllDrives=True, supportsAllDrives=True,
                             fields="files(id)").execute().get("files", [])
    if hit:
        return hit[0]["id"], False
    made = drive.files().create(body={"name": name, "mimeType": mime, "parents": [parent]},
                                supportsAllDrives=True, fields="id").execute()
    return made["id"], True


# Material that has to be real STRUCTURE, not prose that describes structure. `docs-structure`
# asked for a comment on a heading and a comment on a table cell, and the document contained
# neither: "Section Two" was NORMAL_TEXT and there were ZERO tables in it (found 2026-09-08,
# by trying to follow the specimen's own instructions). A specimen that cannot be used the way
# it tells you to use it is worse than a missing one — you go looking for your own mistake.
#
# Keyed by specimen name -> lines in `material` that must become real headings.
MATERIAL_HEADINGS = {
    "docs-structure": ["Section Two"],
}

# Specimens needing a real table appended to their material, with its contents.
MATERIAL_TABLES = {
    "docs-structure": [["Region", "Q3 actual"], ["Southwest", "388000"], ["Northeast", "412000"]],
}


def write_body(docs, file_id: str, text: str, name: str = "") -> None:
    """Insert the text, then style the headings and add any structural material.

    One insert at index 1, so a character offset in `text` is simply `1 + offset` — reliable
    arithmetic, unlike inserting paragraph by paragraph and tracking a moving cursor.
    """
    docs.documents().batchUpdate(documentId=file_id, body={"requests": [
        {"insertText": {"location": {"index": 1}, "text": text}}]}).execute()
    requests = []
    for heading in HEADINGS:
        at = text.find(heading)
        if at < 0:
            continue
        requests.append({"updateParagraphStyle": {
            "range": {"startIndex": 1 + at, "endIndex": 1 + at + len(heading)},
            "paragraphStyle": {"namedStyleType": "HEADING_1"},
            "fields": "namedStyleType"}})
    # The title line, so the specimen reads as a document rather than a wall of text.
    first = text.split("\n", 1)[0]
    requests.append({"updateParagraphStyle": {
        "range": {"startIndex": 1, "endIndex": 1 + len(first)},
        "paragraphStyle": {"namedStyleType": "TITLE"}, "fields": "namedStyleType"}})
    # Material headings, styled the same way as the section headings above.
    #
    # Matched as a WHOLE LINE. A bare `text.find(heading)` styled the wrong paragraph: the
    # by_hand instruction reads "- Comment on the heading 'Section Two' below.", which occurs
    # FIRST, so the instruction became the heading and the material stayed plain. Section
    # headings escape this only because their names happen to be unique in the document.
    for heading in MATERIAL_HEADINGS.get(name, []):
        at = text.find(f"\n{heading}\n")
        if at < 0:
            continue
        at += 1                                    # past the leading newline
        requests.append({"updateParagraphStyle": {
            "range": {"startIndex": 1 + at, "endIndex": 1 + at + len(heading)},
            "paragraphStyle": {"namedStyleType": "HEADING_2"},
            "fields": "namedStyleType"}})
    if requests:
        docs.documents().batchUpdate(documentId=file_id,
                                     body={"requests": requests}).execute()

    # The table goes in LAST and at the END, in its own call. Inserting it earlier would shift
    # every offset the heading styling above depends on, and `insertTable` returns no id, so
    # the only reliable way to fill it is to re-read the document and address the cells by the
    # indices Docs assigned.
    rows = MATERIAL_TABLES.get(name)
    if rows:
        _append_table(docs, file_id, rows)


def _append_table(docs, file_id: str, rows: list[list[str]]) -> None:
    """Append a real table and fill it, addressing cells by re-read indices.

    Filling it needs the SECOND read: `insertTable` reports nothing about where the cells
    landed, and cell start indices are not derivable from the table's own start — an empty
    cell still occupies indices, and they shift as earlier cells are filled. So the writes go
    in REVERSE document order, which keeps every not-yet-written index valid.
    """
    doc = docs.documents().get(documentId=file_id, fields="body(content(endIndex))").execute()
    end = (doc.get("body", {}).get("content") or [{}])[-1].get("endIndex", 2)
    docs.documents().batchUpdate(documentId=file_id, body={"requests": [
        {"insertText": {"location": {"index": end - 1}, "text": "\n"}},
        {"insertTable": {"rows": len(rows), "columns": len(rows[0]),
                         "location": {"index": end}}}]}).execute()

    doc = docs.documents().get(documentId=file_id, includeTabsContent=True).execute()
    body = doc["tabs"][0]["documentTab"]["body"] if "tabs" in doc else doc["body"]
    table = [el for el in body["content"] if "table" in el][-1]["table"]

    cells = []
    for r, row in enumerate(table["tableRows"]):
        for c, cell in enumerate(row["tableCells"]):
            para = [x for x in cell["content"] if "paragraph" in x][0]
            cells.append((para["startIndex"], rows[r][c]))
    requests = [{"insertText": {"location": {"index": i}, "text": t}}
                for i, t in sorted(cells, reverse=True)]          # reverse: indices stay valid
    docs.documents().batchUpdate(documentId=file_id, body={"requests": requests}).execute()


def api_comments(drive, file_id: str, spec: dict) -> list[str]:
    """The comments only the API can make. Everything else needs the editor.

    Each carries its own explanation in its body, for the same reason the documents do: a
    reader looking at the sidebar should not have to hold a separate key.
    """
    made = []
    plan = [
        ("A - FILE-LEVEL: no anchor and no quoted text. This is what a comment about the "
         "whole document looks like. Created through the Drive API.", None),
        ("B - QUOTE-ONLY: quoted text and NO anchor. Only the API can make this. In the "
         "editor it renders as 'Original content deleted' and the quote is not shown, which "
         "is why 4 of 90 threads on a real document went unnoticed in this state.",
         spec.get("quote_present")),
        ("C - QUOTE-ONLY, AND THE QUOTE IS FALSE: the text below is not in this document. "
         "Drive validates that field against nothing, so a comment can attribute words to a "
         "document that never contained them. Do not trust quoted_text as evidence.",
         "THIS TEXT DOES NOT APPEAR ANYWHERE IN THIS DOCUMENT"),
    ]
    for content, quote in plan:
        if quote is None and content.startswith("B "):
            continue
        payload: dict = {"content": content}
        if quote:
            payload["quotedFileContent"] = {"mimeType": "text/html", "value": quote}
        out = drive.comments().create(fileId=file_id, body=payload, fields="id").execute()
        made.append(out["id"])
    return made


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rewrite", action="store_true",
                    help="rewrite the body of an EXISTING specimen. Shifts every character "
                         "index, so it breaks every hand-placed anchor on that file.")
    ap.add_argument("--comments", action="store_true",
                    help="place the API-creatable comments (only on files created this run, "
                         "unless --rewrite)")
    args = ap.parse_args()

    drive, docs = services()
    drive_id = find_drive(drive)
    top, _ = find_or_make(drive, TOP, drive_id, drive_id, FOLDER)
    sub, _ = find_or_make(drive, SUB, top, drive_id, FOLDER)
    print(f"drive  {drive_id}\ntop    {top}\ncomments {sub}\n")

    # A folder-level README, so somebody arriving at the link is not guessing. Lives in the
    # TOP folder rather than in `comments/`, because it describes the whole corpus and the
    # corpus will grow past comments.
    readme, made = find_or_make(drive, "README - what this folder is", top, drive_id, DOC)
    if made or args.rewrite:
        if not made:
            doc = docs.documents().get(documentId=readme,
                                       fields="body(content(endIndex))").execute()
            end = (doc.get("body", {}).get("content") or [{}])[-1].get("endIndex", 2)
            if end > 2:
                docs.documents().batchUpdate(documentId=readme, body={"requests": [
                    {"deleteContentRange": {"range": {"startIndex": 1,
                                                      "endIndex": end - 1}}}]}).execute()
        write_body(docs, readme, README, "README")
    print(f"  {'created' if made else 'exists ':<8} {'README':<26} {readme}\n")

    manifest = []
    for name, spec in SPECIMENS.items():
        text = body(spec["title"], spec["what"], spec["why"], spec["look"],
                    spec["by_hand"], spec["material"], date=TODAY, axis="docs")
        # The quote a quote-only comment will carry: real text from this document, so the
        # specimen shows an HONEST quote-only comment beside a fabricated one.
        spec = dict(spec, quote_present=spec["material"][0][:80])
        fid, created = find_or_make(drive, name, sub, drive_id, DOC)
        if created or args.rewrite:
            if not created:
                print(f"  {name}: REWRITING body - hand-placed anchors on this file will break")
                doc = docs.documents().get(documentId=fid, fields="body(content(endIndex))").execute()
                end = (doc.get("body", {}).get("content") or [{}])[-1].get("endIndex", 2)
                if end > 2:
                    docs.documents().batchUpdate(documentId=fid, body={"requests": [
                        {"deleteContentRange": {"range": {"startIndex": 1,
                                                          "endIndex": end - 1}}}]}).execute()
            write_body(docs, fid, text, name)
        cids = api_comments(drive, fid, spec) if (args.comments and (created or args.rewrite)) else []
        print(f"  {'created' if created else 'exists ':<8} {name:<26} {fid}"
              f"{'  +' + str(len(cids)) + ' comments' if cids else ''}")
        manifest.append({"name": name, "id": fid, "title": spec["title"],
                         "url": f"https://docs.google.com/document/d/{fid}/edit",
                         "hand_placement_outstanding": spec["by_hand"]})

    out = os.path.join(os.path.dirname(__file__), "manifest.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"drive": drive_id, "folder_top": top, "folder_comments": sub,
                   "readme": readme, "specimens": manifest}, fh, indent=2)
        fh.write("\n")
    print(f"\nmanifest -> {out}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HttpError as e:
        print(f"\nDrive refused: {e}", file=sys.stderr)
        raise SystemExit(1) from e

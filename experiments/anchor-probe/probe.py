#!/usr/bin/env python3
"""
Empirically probe how Google Sheets comment *anchors* behave via the Drive API.

This settles three questions the research currently answers only from documentation:

  A. CREATE  — When you create a comment via the Drive API with a cell anchor,
               does the Sheets UI show it on the cell, or file-level (unanchored)?
  B. DUMP    — What does the RAW `anchor` string of a comment placed ON A CELL in
               the Sheets UI actually look like? (Is it parseable to A1, or opaque?)
  C. XLSX    — Does exporting the sheet as XLSX expose comments with A1 refs
               (the reverse-engineered read path), and in which XML part?

Question B is the important one: it tells us whether the "anchors are opaque, use
XLSX-export" conclusion in google-drive-comments-reference.md is correct, or whether
a real parseable Sheets anchor structure exists (as one MCP server's code implies).

Usage:
    python probe.py --file-id <SPREADSHEET_ID> --all
    python probe.py --file-id <ID> --dump                 # just Test B
    python probe.py --file-id <ID> --create --cell B11    # just Test A

Setup: see README.md in this directory (OAuth client + `pip install -r requirements.txt`).
Run against a THROWAWAY spreadsheet you own. Test A writes a comment.
"""
import argparse
import io
import json
import os
import re
import zipfile

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive"]
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# Every comments/replies method except delete REQUIRES a fields spec (see reference doc).
# Replies MUST be expanded with subfields or the API returns them empty.
COMMENT_FIELDS = (
    "comments(id,anchor,content,quotedFileContent,resolved,createdTime,"
    "author(displayName,emailAddress),"
    "replies(id,createdTime,action,deleted,content,author(displayName))),"
    "nextPageToken"
)


def get_drive():
    """OAuth once, cache the token in token.json for subsequent runs."""
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def col_letter_to_index(letters):
    idx = 0
    for ch in letters.upper():
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1  # 0-based


def parse_a1(cell):
    m = re.fullmatch(r"([A-Za-z]+)(\d+)", cell.strip())
    if not m:
        raise ValueError(f"Bad A1 cell reference: {cell!r}")
    return int(m.group(2)) - 1, col_letter_to_index(m.group(1))  # (row0, col0)


def test_create(drive, file_id, cell):
    """Test A — create a comment with a cell anchor and see what comes back."""
    print(f"\n=== TEST A: create anchored comment on {cell} ===")
    row0, col0 = parse_a1(cell)
    # Candidate anchor shape a real MCP server (a-bonus/google-docs-mcp) parses on read.
    # We send it and observe whether Google honors / echoes / rewrites it.
    anchor = json.dumps({"r": "head", "a": [{"sht": {"sid": 0, "rng": {"r": row0, "c": col0}}}]})
    body = {"content": f"[anchor-probe] test comment targeting {cell}", "anchor": anchor}
    created = drive.comments().create(
        fileId=file_id, body=body, fields="id,anchor,content"
    ).execute()
    print("Sent anchor:   ", anchor)
    print("Created id:    ", created.get("id"))
    print("Echoed anchor: ", repr(created.get("anchor")))
    print(">>> ACTION: open the sheet in the browser. Is this comment shown ON",
          f"cell {cell}, or in the file-level 'All comments' pane (unanchored)?")


def test_dump(drive, file_id):
    """Test B — dump raw anchors of ALL existing comments (place some on cells in the UI first)."""
    print("\n=== TEST B: dump raw anchors of existing comments ===")
    print("(Place a comment on a cell in the Sheets UI BEFORE running this to see a real anchor.)")
    page_token = None
    n = 0
    while True:
        resp = drive.comments().list(
            fileId=file_id, fields=COMMENT_FIELDS,
            pageSize=100, includeDeleted=False, pageToken=page_token,
        ).execute()
        for c in resp.get("comments", []):
            n += 1
            author = (c.get("author") or {}).get("displayName", "?")
            print(f"\n--- comment {c.get('id')} ---")
            print("  author:           ", author)
            print("  content:          ", (c.get("content") or "")[:80])
            print("  RAW anchor:       ", repr(c.get("anchor")))  # <-- the key datum
            print("  quotedFileContent:", json.dumps(c.get("quotedFileContent")))
            print("  resolved:         ", c.get("resolved"))
            replies = c.get("replies", [])
            print(f"  replies:           {len(replies)}")
            for r in replies:  # replies come back in chronological order
                who = (r.get("author") or {}).get("displayName", "?")
                act = f" [action={r['action']}]" if r.get("action") else ""
                body = "(deleted)" if r.get("deleted") else (r.get("content") or "")[:100]
                print(f"    - {r.get('createdTime')} {who}{act}: {body}")
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    print(f"\nTotal comments: {n}. Compare the RAW anchor strings against the",
          "reference doc's 'anchors are opaque' claim.")


def test_xlsx(drive, file_id):
    """Test C — export as XLSX and inspect which parts carry comments + A1 refs."""
    print("\n=== TEST C: XLSX export comment parts ===")
    data = drive.files().export(fileId=file_id, mimeType=XLSX_MIME).execute()
    zf = zipfile.ZipFile(io.BytesIO(data))
    comment_parts = [n for n in zf.namelist()
                     if "comment" in n.lower()]  # xl/comments*.xml, xl/threadedComments*.xml
    if not comment_parts:
        print("  No comment parts found in the XLSX export.")
        print("  All parts:", zf.namelist())
        return
    for part in comment_parts:
        xml = zf.read(part).decode("utf-8", "replace")
        refs = re.findall(r'ref="([^"]+)"', xml)  # Excel stores each comment against an A1 ref
        print(f"\n--- {part} ---")
        print("  A1 refs found:", refs or "(none — check the raw XML below)")
        if "threadedComment" in part:
            # A thread = a root threadedComment plus replies that carry parentId.
            print("  thread structure (parentId links replies to their root):")
            for m in re.finditer(
                r"<[\w:]*threadedComment\b([^>]*)>.*?<[\w:]*text[^>]*>(.*?)</[\w:]*text>",
                xml, re.S,
            ):
                a = dict(re.findall(r'([\w:]+)="([^"]*)"', m.group(1)))
                short = lambda v: (v or "").strip("{}")[:8]
                kind = "reply" if a.get("parentId") else "ROOT "
                print(f"    [{kind}] ref={a.get('ref')} id={short(a.get('id'))}"
                      f" parent={short(a.get('parentId')) or '-'} done={a.get('done')}"
                      f": {m.group(2)[:90]}")
        else:
            print("  raw (first 1000 chars):\n", xml[:1000])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file-id", required=True, help="Spreadsheet (Drive file) ID")
    ap.add_argument("--cell", default="B11", help="Cell for the create test (default B11)")
    ap.add_argument("--create", action="store_true", help="Run Test A (writes a comment)")
    ap.add_argument("--dump", action="store_true", help="Run Test B")
    ap.add_argument("--xlsx", action="store_true", help="Run Test C")
    ap.add_argument("--all", action="store_true", help="Run all three")
    args = ap.parse_args()

    drive = get_drive()
    if args.all or args.dump:
        test_dump(drive, args.file_id)
    if args.all or args.create:
        test_create(drive, args.file_id, args.cell)
    if args.all or args.xlsx:
        test_xlsx(drive, args.file_id)
    if not (args.all or args.dump or args.create or args.xlsx):
        ap.error("pick at least one of --dump / --create / --xlsx / --all")


if __name__ == "__main__":
    main()

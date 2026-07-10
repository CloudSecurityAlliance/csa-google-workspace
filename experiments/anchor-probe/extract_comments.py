#!/usr/bin/env python3
"""
Extract ALL comments from ANY Google Drive file into structured JSON.

Works for any file type the Drive API exposes comments on — Google Docs, Sheets,
Slides, Drawings, and non-Google "blob" files (PDF, images, uploaded .docx, ...).
Comment *listing* is universal; *cell-location* resolution is Sheets-only (there is
no reliable A1 in the Drive anchor — see ../../research/google-drive-comments-reference.md).

Each comment is emitted with: author info, timestamps, content, resolved/deleted
state, quotedFileContent, the raw anchor, and its full reply thread (chronological,
with resolve/reopen actions). For Sheets, an A1 `cell` is added best-effort by
exporting XLSX and matching root comments by text.

Usage:
    python extract_comments.py --file-id <ID>                 # JSON to stdout
    python extract_comments.py --file-id <ID> --out out.json  # to a file
    python extract_comments.py --file-id <ID> --include-deleted

Auth: reuses credentials.json / token.json in this directory (same as probe.py).
"""
import argparse
import io
import json
import re
import sys
import zipfile
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

TYPE_BY_MIME = {
    "application/vnd.google-apps.spreadsheet": "sheet",
    "application/vnd.google-apps.document": "document",
    "application/vnd.google-apps.presentation": "presentation",
    "application/vnd.google-apps.drawing": "drawing",
}

_USER = "author(displayName,emailAddress,me,photoLink)"
COMMENT_FIELDS = (
    "nextPageToken,comments("
    f"id,anchor,content,htmlContent,quotedFileContent,resolved,deleted,createdTime,modifiedTime,{_USER},"
    f"replies(id,content,htmlContent,action,deleted,createdTime,modifiedTime,{_USER})"
    ")"
)


def get_drive():
    creds = None
    try:
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    except Exception:
        pass
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def fetch_file_meta(drive, file_id):
    m = drive.files().get(
        fileId=file_id, fields="id,name,mimeType,webViewLink", supportsAllDrives=True
    ).execute()
    m["type"] = TYPE_BY_MIME.get(m.get("mimeType"), "blob")
    return m


def fetch_comments(drive, file_id, include_deleted):
    out, page_token = [], None
    while True:
        resp = drive.comments().list(
            fileId=file_id, fields=COMMENT_FIELDS, pageSize=100,
            includeDeleted=include_deleted, pageToken=page_token,
        ).execute()
        out.extend(resp.get("comments", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


def sheet_cell_map(drive, file_id):
    """Sheets only: {root_comment_text -> A1 ref} parsed from the XLSX export.

    The Drive anchor's `range` is an opaque id, so we recover the cell from the
    exported threaded-comments XML and join back to Drive comments by text. This
    is best-effort: ambiguous when two root comments share identical text.
    """
    data = drive.files().export(fileId=file_id, mimeType=XLSX_MIME).execute()
    zf = zipfile.ZipFile(io.BytesIO(data))
    mapping, seen, ambiguous = {}, set(), set()
    for name in zf.namelist():
        if "threadedComments" not in name:
            continue
        xml = zf.read(name).decode("utf-8", "replace")
        for m in re.finditer(
            r"<[\w:]*threadedComment\b([^>]*)>.*?<[\w:]*text[^>]*>(.*?)</[\w:]*text>",
            xml, re.S,
        ):
            attrs = dict(re.findall(r'([\w:]+)="([^"]*)"', m.group(1)))
            if attrs.get("parentId"):
                continue  # replies inherit the root's ref; only map roots
            text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            ref = attrs.get("ref")
            if text in seen and mapping.get(text) != ref:
                ambiguous.add(text)
            seen.add(text)
            mapping[text] = ref
    for t in ambiguous:
        mapping.pop(t, None)  # don't guess when duplicate texts collide
    return mapping


def norm_reply(r):
    return {
        "id": r.get("id"),
        "author": r.get("author"),
        "createdTime": r.get("createdTime"),
        "modifiedTime": r.get("modifiedTime"),
        "action": r.get("action") or None,  # "resolve" | "reopen" | None
        "deleted": bool(r.get("deleted")),
        "content": r.get("content"),
        "htmlContent": r.get("htmlContent"),
    }


def assemble(drive, file_id, include_deleted):
    meta = fetch_file_meta(drive, file_id)
    comments = fetch_comments(drive, file_id, include_deleted)
    cell_map = sheet_cell_map(drive, file_id) if meta["type"] == "sheet" else {}

    out_comments, warnings = [], []
    for c in comments:
        cell = cell_map.get((c.get("content") or "").strip()) if cell_map else None
        if meta["type"] == "sheet" and cell is None and not c.get("deleted"):
            warnings.append(f"comment {c.get('id')}: no A1 cell resolved (unanchored, or text didn't match XLSX export)")
        out_comments.append({
            "id": c.get("id"),
            "author": c.get("author"),
            "createdTime": c.get("createdTime"),
            "modifiedTime": c.get("modifiedTime"),
            "resolved": bool(c.get("resolved")),
            "deleted": bool(c.get("deleted")),
            "content": c.get("content"),
            "htmlContent": c.get("htmlContent"),
            "quotedFileContent": c.get("quotedFileContent"),
            "anchor": {
                "raw": c.get("anchor"),               # opaque for Sheets; text-region for Docs
                "cell": cell,                          # A1, Sheets-only, best-effort
            },
            "replies": [norm_reply(r) for r in c.get("replies", [])],
        })

    return {
        "file": meta,
        "extractedAt": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "comments": len(out_comments),
            "open": sum(1 for c in out_comments if not c["resolved"] and not c["deleted"]),
            "resolved": sum(1 for c in out_comments if c["resolved"]),
            "replies": sum(len(c["replies"]) for c in out_comments),
        },
        "comments": out_comments,
        "_warnings": warnings,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file-id", required=True)
    ap.add_argument("--out", help="write JSON here instead of stdout")
    ap.add_argument("--include-deleted", action="store_true")
    args = ap.parse_args()

    result = assemble(get_drive(), args.file_id, args.include_deleted)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        c = result["counts"]
        print(f"Wrote {args.out}: {c['comments']} comments, {c['replies']} replies "
              f"({c['open']} open, {c['resolved']} resolved). "
              f"{len(result['_warnings'])} warning(s).", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Comment LIFECYCLE probe — Drive API v3.

Empirically settles the comment/reply lifecycle semantics the library design
rests on, by exercising the whole cycle on a SELF-CREATED throwaway Google Sheet
and capturing the raw API responses at every step. The fixture is trashed at the
end (reversible), so the probe leaves nothing behind.

Questions (see RESULTS.md for measured answers):
  Q1  On create, is `resolved` present/false by default? is `deleted`?
  Q2  Does author carry a `me` boolean? is `emailAddress` returned when asked?
  Q3  RESOLVE — does a reply with action=resolve flip comment.resolved -> true?
  Q4  Can an action reply be CONTENT-LESS (so .resolve() need not force text)?
  Q5  REOPEN — does action=reopen flip resolved back to false?
  Q6  Can we EDIT our own comment (comments.update) and reply (replies.update)?
  Q7  DELETE — soft? content AND author stripped? gone from the default list?

Auth: reuses the OAuth client + cached token from a sibling probe dir by default
(../anchor-probe), or pass --creds-dir. Needs the `drive` scope.

    python probe_lifecycle.py                 # runs the full cycle
    python probe_lifecycle.py --creds-dir ../anchor-probe
"""
import argparse
import json
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/drive"]
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
CFIELDS = ("id,anchor,content,htmlContent,resolved,deleted,createdTime,modifiedTime,"
           "author(displayName,emailAddress,me),quotedFileContent,"
           "replies(id,content,htmlContent,action,deleted,createdTime,author(displayName,me))")
RFIELDS = "id,content,htmlContent,action,deleted,createdTime,author(displayName,me)"

transcript = []


def rec(step, note, payload):
    transcript.append({"step": step, "note": note, "data": payload})
    print(f"\n=== {step}: {note} ===")
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def get_drive(creds_dir):
    token = os.path.join(creds_dir, "token_full.json")
    if not os.path.exists(token):
        token = os.path.join(creds_dir, "token.json")
    client = os.path.join(creds_dir, "credentials.json")
    creds = None
    if os.path.exists(token):
        creds = Credentials.from_authorized_user_file(token, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            open(token, "w").write(creds.to_json())
        else:
            from google_auth_oauthlib.flow import InstalledAppFlow
            creds = InstalledAppFlow.from_client_secrets_file(client, SCOPES).run_local_server(port=0)
            open(token, "w").write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--creds-dir", default=os.path.join(os.path.dirname(__file__), "..", "anchor-probe"))
    args = ap.parse_args()
    d = get_drive(args.creds_dir)

    fid = None
    try:
        f = d.files().create(body={"name": "PROBE-lifecycle-THROWAWAY", "mimeType": SHEET_MIME},
                             fields="id,name,webViewLink").execute()
        fid = f["id"]
        rec("SETUP", "created throwaway sheet", f)

        c = d.comments().create(fileId=fid, body={"content": "probe comment ONE"}, fields=CFIELDS).execute()
        cid = c["id"]
        rec("Q1/Q2", "comments.create (note resolved/deleted defaults, author.me, emailAddress)", c)

        r1 = d.replies().create(fileId=fid, commentId=cid, body={"content": "a normal reply"},
                                fields=RFIELDS).execute()
        rec("REPLY", "replies.create (plain reply, no action)", r1)

        # Q4 — action reply with EMPTY content
        try:
            rr = d.replies().create(fileId=fid, commentId=cid, body={"action": "resolve"},
                                    fields=RFIELDS).execute()
            rec("Q4", "replies.create action=resolve, NO content -> ALLOWED", rr)
        except HttpError as e:
            rec("Q4", "replies.create action=resolve, NO content -> REJECTED", {"error": str(e)})
            d.replies().create(fileId=fid, commentId=cid, body={"action": "resolve", "content": "resolving"},
                               fields=RFIELDS).execute()

        rec("Q3", "comments.get after resolve (resolved should be true)",
            d.comments().get(fileId=fid, commentId=cid, fields=CFIELDS).execute())

        d.replies().create(fileId=fid, commentId=cid, body={"action": "reopen"}, fields=RFIELDS).execute()
        rec("Q5", "comments.get after reopen (resolved should be false)",
            d.comments().get(fileId=fid, commentId=cid, fields=CFIELDS).execute())

        ce = d.comments().update(fileId=fid, commentId=cid, body={"content": "probe comment ONE (edited)"},
                                 fields=CFIELDS).execute()
        rec("Q6a", "comments.update own comment", {"content": ce.get("content"), "modifiedTime": ce.get("modifiedTime")})
        re_ = d.replies().update(fileId=fid, commentId=cid, replyId=r1["id"],
                                 body={"content": "a normal reply (edited)"}, fields=RFIELDS).execute()
        rec("Q6b", "replies.update own reply", {"content": re_.get("content")})

        d.comments().delete(fileId=fid, commentId=cid).execute()
        rec("Q7a", "comments.delete returned (204, no body)", {"ok": True})
        rec("Q7b", "comments.list includeDeleted=FALSE (default)",
            d.comments().list(fileId=fid, fields=f"comments({CFIELDS})").execute())
        rec("Q7c", "comments.list includeDeleted=TRUE (expect deleted=true, content+author stripped)",
            d.comments().list(fileId=fid, includeDeleted=True, fields=f"comments({CFIELDS})").execute())
    finally:
        out = os.path.join(os.path.dirname(__file__), "lifecycle_transcript.json")
        json.dump(transcript, open(out, "w"), indent=2, ensure_ascii=False, default=str)
        print(f"\n[transcript: {out}]")
        if fid:
            try:
                d.files().update(fileId=fid, body={"trashed": True}).execute()
                print(f"[fixture {fid} moved to TRASH (reversible)]")
            except HttpError as e:
                print(f"[WARN: could not trash fixture {fid}: {e}]")


if __name__ == "__main__":
    main()

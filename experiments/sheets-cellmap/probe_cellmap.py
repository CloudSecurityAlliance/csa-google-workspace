#!/usr/bin/env python3
"""
Sheets cell-mapping probe — the real XLSX comment structure + export size.

Settles what the Phase-4 cell-mapper must parse: creates a throwaway Sheet, adds a
couple of API comments (with a reply), exports XLSX, and dumps the actual
`xl/threadedComments/*.xml` + `xl/persons/*.xml` + legacy `xl/comments*.xml`. Also
exports a large sheet for a size data point vs Google's ~10 MB export cap. Trashes
the fixtures. Standalone (raw google client); reuses the anchor-probe OAuth token.

    python probe_cellmap.py --creds-dir ../anchor-probe
"""
import argparse, io, os, zipfile
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SHEET = "application/vnd.google-apps.spreadsheet"


def creds_from(creds_dir):
    token = os.path.join(creds_dir, "token_full.json")
    c = Credentials.from_authorized_user_file(token, SCOPES)
    if not c.valid and c.expired and c.refresh_token:
        c.refresh(Request()); open(token, "w").write(c.to_json())
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--creds-dir", default=os.path.join(os.path.dirname(__file__), "..", "anchor-probe"))
    args = ap.parse_args()
    c = creds_from(args.creds_dir)
    drive = build("drive", "v3", credentials=c)
    sheets = build("sheets", "v4", credentials=c)

    created = []
    def mk(name):
        fid = drive.files().create(body={"name": name, "mimeType": SHEET}, fields="id").execute()["id"]
        created.append(fid); return fid

    try:
        sid = mk("PROBE-cellmap-THROWAWAY")
        sheets.spreadsheets().values().update(
            spreadsheetId=sid, range="A1", valueInputOption="RAW",
            body={"values": [["Region", "Q1"], ["West", "100"], ["East", "200"]]}).execute()
        c1 = drive.comments().create(fileId=sid, body={"content": "Is West number right?"},
                                     fields="id,createdTime,author(displayName)").execute()
        drive.replies().create(fileId=sid, commentId=c1["id"], body={"content": "checking now"}, fields="id").execute()
        c2 = drive.comments().create(fileId=sid, body={"content": "East looks high"},
                                     fields="id,createdTime,author(displayName)").execute()
        print("=== Drive comments ===")
        for cc in (c1, c2):
            print(f"  {cc['id']}  createdTime={cc.get('createdTime')}  author={cc.get('author')}  {cc['content']!r}")

        data = drive.files().export(fileId=sid, mimeType=XLSX).execute()
        print(f"\n=== XLSX export: {len(data)} bytes ===")
        z = zipfile.ZipFile(io.BytesIO(data))
        for n in z.namelist():
            if "threadedComment" in n or "persons" in n or n.endswith("comments1.xml"):
                print(f"\n----- {n} -----\n{z.read(n).decode('utf-8', 'replace')[:2000]}")

        big = mk("PROBE-cellmap-BIG-THROWAWAY")
        sheets.spreadsheets().values().update(
            spreadsheetId=big, range="A1", valueInputOption="RAW",
            body={"values": [[f"r{r}c{col}" for col in range(15)] for r in range(8000)]}).execute()
        big_data = drive.files().export(fileId=big, mimeType=XLSX).execute()
        print(f"\n=== BIG (8000x15=120k cells) export: {len(big_data)} bytes "
              f"({len(big_data)/1_000_000:.2f} MB); Google export cap ~10 MB ===")
    finally:
        for fid in created:
            try:
                drive.files().update(fileId=fid, body={"trashed": True}).execute()
            except Exception as e:
                print("WARN trash", fid, e)
        print(f"[trashed {len(created)} throwaway files]")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Docs SUGGESTIONS probe — Docs API v1.

Settles whether "suggesting mode" edits can be read and/or accepted/rejected
programmatically. Reads a Doc in all three suggestionsViewMode values, extracts
the suggested edits, and — decisively — enumerates the ENTIRE Docs API surface
(every documents.* method + every batchUpdate Request type) to prove whether an
accept/reject operation exists at all, rather than trusting documentation.

Requires a Doc that already contains suggesting-mode edits (suggestions can only
be created in the UI — there is no API to create one). Needs the `documents`
scope AND the Google Docs API enabled in the Cloud project.

    python probe_suggestions.py --doc-id <DOCUMENT_ID>
    python probe_suggestions.py --doc-id <ID> --creds-dir ../anchor-probe
"""
import argparse
import json
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/drive",
          "https://www.googleapis.com/auth/documents"]

transcript = {}


def rec(k, v):
    transcript[k] = v
    print(f"\n=== {k} ===")
    print(json.dumps(v, indent=2, ensure_ascii=False)[:4000])


def get_creds(creds_dir):
    token = os.path.join(creds_dir, "token_full.json")
    creds = Credentials.from_authorized_user_file(token, SCOPES)
    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        open(token, "w").write(creds.to_json())
    return creds


def walk_text(doc):
    """Return (plain_text, suggestions[]) from a document dict."""
    text, sugg = [], []
    for el in doc.get("body", {}).get("content", []):
        para = el.get("paragraph")
        if not para:
            continue
        for pe in para.get("elements", []):
            tr = pe.get("textRun")
            if not tr:
                continue
            text.append(tr.get("content", ""))
            ins, dele = tr.get("suggestedInsertionIds"), tr.get("suggestedDeletionIds")
            if ins or dele:
                sugg.append({
                    "text": tr.get("content", ""),
                    "kind": "insertion" if ins else "deletion",
                    "suggestedInsertionIds": ins,
                    "suggestedDeletionIds": dele,
                    "other_keys": [k for k in tr.keys()
                                   if k not in ("content", "textStyle",
                                                "suggestedInsertionIds", "suggestedDeletionIds")],
                })
    return "".join(text), sugg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc-id", required=True)
    ap.add_argument("--creds-dir", default=os.path.join(os.path.dirname(__file__), "..", "anchor-probe"))
    args = ap.parse_args()

    creds = get_creds(args.creds_dir)
    docs = build("docs", "v1", credentials=creds)

    try:
        d_inline = docs.documents().get(documentId=args.doc_id,
                                        suggestionsViewMode="SUGGESTIONS_INLINE").execute()
    except HttpError as e:
        rec("FATAL", {"error": str(e),
                      "hint": "403 SERVICE_DISABLED -> enable the Google Docs API in the GCP project"})
        return

    txt, sugg = walk_text(d_inline)
    rec("S1_inline_text", {"text": txt})
    rec("S1/S3_suggestions", {"count": len(sugg), "suggestions": sugg,
                              "note": "one logical suggestion may span multiple runs (same id); "
                                      "'other_keys' shows there is no author/time on a run"})
    rec("S3_doc_level_keys", {"top_level_keys": sorted(d_inline.keys())})

    for mode in ("PREVIEW_SUGGESTIONS_ACCEPTED", "PREVIEW_WITHOUT_SUGGESTIONS"):
        t, _ = walk_text(docs.documents().get(documentId=args.doc_id, suggestionsViewMode=mode).execute())
        rec(f"S2_{mode}", {"text": t})

    rd = docs._rootDesc
    req_types = sorted(rd["schemas"]["Request"]["properties"].keys())
    methods = sorted(rd["resources"]["documents"]["methods"].keys())
    sugg_reqs = [r for r in req_types if "suggest" in r.lower()]
    sugg_methods = [m for m in methods if any(w in m.lower() for w in ("suggest", "accept", "reject"))]
    rec("S4_docs_api_surface", {
        "all_documents_methods": methods,
        "batchUpdate_request_type_count": len(req_types),
        "all_batchUpdate_request_types": req_types,
        "suggestion_related_request_types": sugg_reqs,
        "accept_or_reject_methods": sugg_methods,
        "VERDICT": "NO accept/reject endpoint exists" if not sugg_reqs and not sugg_methods
                   else f"found: {sugg_reqs + sugg_methods}",
    })

    drive = build("drive", "v3", credentials=creds)
    rec("S5_drive_comments_on_doc", drive.comments().list(
        fileId=args.doc_id, includeDeleted=False,
        fields="comments(id,content,quotedFileContent,anchor,resolved,"
               "author(displayName,me),replies(content,action))").execute())

    out = os.path.join(os.path.dirname(__file__), "suggestions_transcript.json")
    json.dump(transcript, open(out, "w"), indent=2, ensure_ascii=False)
    print(f"\n[transcript: {out}]")


if __name__ == "__main__":
    main()

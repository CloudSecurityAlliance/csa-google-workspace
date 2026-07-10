# Anchor Probe

A ~180-line script to **empirically settle how Google Sheets comment anchors behave** via the Drive API — the one part of the research confirmed only from documentation, not first-hand.

It runs three tests:

| Test | Flag | What it answers |
|------|------|-----------------|
| **A — create** | `--create` | Create a comment with a cell anchor. Does the Sheets UI show it on the cell, or file-level (unanchored)? |
| **B — dump** | `--dump` | Dump the **raw `anchor` string** of comments placed on cells *in the UI*. Opaque, or parseable to A1? |
| **C — xlsx** | `--xlsx` | Export as XLSX and show which XML part (`xl/comments*.xml` vs `xl/threadedComments*.xml`) carries comments and their A1 `ref`s. |

**Test B is the important one.** It directly checks the [reference doc](../../research/google-drive-comments-reference.md#7-the-anchor-field--the-hard-truth-for-sheets) claim that Sheets anchors are opaque — a claim that at least one MCP server's source code (which parses `{"a":[{"sht":{"sid","rng":{"r","c"}}}]}`) appears to contradict. Whatever the raw string turns out to be, it settles the question and tells us whether the reference doc needs a correction.

## Setup

1. **Create an OAuth client** (one-time): [Google Cloud Console](https://console.cloud.google.com) → enable the **Google Drive API** → *APIs & Services → Credentials → Create OAuth client ID → Desktop app* → download the JSON as `credentials.json` into this directory. (Add your account as a test user on the OAuth consent screen.)
2. **Install deps** (a virtualenv is fine):
   ```bash
   pip install -r requirements.txt
   ```
3. **Prepare a throwaway spreadsheet** you own. For Test B, first open it in the browser and **add a comment on a cell** (e.g. right-click B11 → Comment). Grab its ID from the URL: `docs.google.com/spreadsheets/d/`**`<THIS>`**`/edit`.

## Run

```bash
# All three tests (Test A writes one comment to the sheet):
python probe.py --file-id <SPREADSHEET_ID> --all

# Just inspect real UI-placed anchors (read-only, safe):
python probe.py --file-id <SPREADSHEET_ID> --dump
```

First run opens a browser for OAuth and caches `token.json` locally.

## What to record

Paste back the output — especially **Test B's `RAW anchor:` lines** and **Test A's browser observation** (anchored vs file-level). That's enough to confirm or correct the reference doc, and to note it in `CHANGELOG.md`.

## Notes
- Uses the full `drive` scope because Test A writes. For a read-only run (`--dump`/`--xlsx` only) you can narrow `SCOPES` in `probe.py` to `drive.readonly`.
- `credentials.json` and `token.json` are secrets — they are gitignored. **Do not commit them.**
- This is a throwaway experiment, deliberately in Python (stdlib `zipfile` makes the XLSX test trivial); it is not part of the eventual TypeScript server.

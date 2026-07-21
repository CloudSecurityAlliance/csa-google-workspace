# Experiments — empirical probes

Small, runnable scripts that **settle behavior questions against the live Google
APIs** instead of trusting documentation. Each probe writes its raw findings to a
`RESULTS.md` (dated), which then feeds corrections back into `research/`. This is
the repo's "speak from authority" habit: if a doc and a probe disagree, the probe wins.

## Probes

| Dir | Settles | Key finding |
|-----|---------|-------------|
| [`anchor-probe/`](./anchor-probe/) | How Sheets comment **anchors** behave; XLSX-export read path | Sheets anchor is `workbook-range` — structured but **not** A1-decodable; cell mapping needs XLSX export |
| [`comment-lifecycle/`](./comment-lifecycle/) | Comment/reply **lifecycle** semantics (create/reply/resolve/reopen/edit/delete) | `resolved` is **absent** until first resolved; delete is soft and **strips author+content**; action-replies can be content-less |
| [`docs-suggestions/`](./docs-suggestions/) | Reading vs accepting/rejecting Docs **suggestions** | Reading works (3 view-modes); **no accept/reject endpoint exists** (full API enumeration); suggestion author not exposed |

## Shared setup (one-time)

All probes share one OAuth client and token, kept in `anchor-probe/` and reused by
the others via `--creds-dir ../anchor-probe`.

1. **Create an OAuth client:** [Google Cloud Console](https://console.cloud.google.com)
   → *APIs & Services → Credentials → Create OAuth client ID → **Desktop app*** →
   download JSON as `anchor-probe/credentials.json`. Add your account as a test user
   on the consent screen.
2. **Enable the APIs you'll call** in the same Cloud project — **this is separate from
   OAuth scopes.** A correctly-scoped token still returns `403 SERVICE_DISABLED` until
   the API is enabled:
   - Drive API (all probes) · Docs API (`docs-suggestions`) · Sheets API · Slides API
3. **Install deps:** `pip install -r anchor-probe/requirements.txt`
4. **Authorize.** The Drive-only probes cache `anchor-probe/token.json` on first run.
   The suggestions probe needs the broader scopes (`drive`, `documents`, `spreadsheets`,
   `presentations`) in `anchor-probe/token_full.json` — re-consent by running a flow
   that requests all four (see `docs-suggestions/probe_suggestions.py`).

## Safety & secrets

- `credentials.json`, `token*.json`, and `*_transcript.json` are **gitignored** — they
  hold secrets and can hold real comment content/emails. Never commit them.
- Mutating probes act as **your Google identity**. `comment-lifecycle` confines all
  writes to a throwaway sheet it **creates and trashes** itself; nothing of yours is touched.
- These probes are throwaway research tools (deliberately Python — stdlib `zipfile`
  makes the XLSX test trivial). They are **not** the library; they inform its design.

# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## What this repository is

`csa-google-workspace` — a **Python library** (import name `csa_google_workspace`) for managing **comments** and (planned) **content** on Google **Docs, Sheets, and Slides**. It is **under active, phased development**: research and design are done and merged; the code is being built one reviewed phase at a time.

- **Shipped:** Phase 1 (foundations) + Phase 2 (full comment management). The library can open a Doc/Sheet/Slides by id/URL and list/filter/create/reply/resolve/reopen/edit/soft-delete comments across all three, uniformly.
- **Planned (see `docs/superpowers/plans/`):** content read (`as_text`/`export`, `Doc.paragraphs`/`Sheet.values`/`Slides.slides`), Sheets cell-mapping (`Comment.location`), content write, and reading Docs suggestions.

This is **not** a TypeScript MCP server and **not** comments-only — earlier drafts said so; both are obsolete. An MCP wrapper is possible later but out of scope.

## Where things live

- **`docs/superpowers/specs/2026-07-20-csa-google-workspace-design.md`** — the authoritative design spec (scope, architecture, API surface, error model, phasing). Start here.
- **`docs/superpowers/plans/`** — the phased, bite-sized TDD implementation plans (foundations, comments, …). Each phase is built from its plan.
- **`src/csa_google_workspace/`** — the library (see layout below).
- **`research/`** — canonical API-behavior references: `google-drive-comments-reference.md` (Drive comments), `docs-suggestions-reference.md` (Docs suggestions), `server-landscape.md` (prior art), `mcp-*` (MCP notes, if an MCP wrapper is ever added).
- **`experiments/`** — runnable empirical probes, each with a dated `RESULTS.md`. **Probe beats docs:** when Google's documentation and a probe disagree, the probe wins, and the finding is folded back into `research/`.

## Code layout (`src/csa_google_workspace/`)

- `workspace.py` — `Workspace` entry point + `open()`/`open_by_url()` (MIME-sniff → typed subclass).
- `auth.py` — OAuth installed-app flow, scope selection, re-consent detection.
- `backend.py` — `Backend` protocol; `ApiBackend` (real Google APIs) + `FakeBackend` (in-memory, powers all unit tests).
- `_services.py` — lazy Google API client registry. `_errors.py` — `HttpError`→typed translator + retry.
- `base.py` — `Document` base + `CommentsMixin`. `documents/` — `Doc`/`Sheet`/`Slides`.
- `comments.py` — `Author`/`Reply`/`Comment`/`CommentCollection` + in-place mutation.
- `exceptions.py` — typed error hierarchy.

## Critical architectural facts

1. **Comments are a Google Drive API v3 concern**, uniform across Docs/Sheets/Slides — one API for all three (the "uniform axis"). Content is the "variant axis" (three separate APIs: Docs v1, Sheets v4, Slides v1). Sheets *notes* are a different, out-of-scope thing.
2. **Probe-verified comment quirks the code depends on** (see `experiments/comment-lifecycle/`): `resolved` is **absent** on a never-resolved comment → treat missing as `False`; soft-delete strips **both `content` and `author`** (models are `Optional`); resolve/reopen is an **action-reply** (never a PATCH) and may be **content-less**; `author.email` is usually absent even when requested.
3. **Sheets `anchor` is `workbook-range` — structured but NOT A1-decodable** (opaque range id). You cannot create a cell-anchored comment via the API, and mapping a comment→cell requires an **XLSX-export-and-parse** detour (Phase 4). Earlier "`R1C2`/parse-to-A1" framing was debunked folklore. See `research/google-drive-comments-reference.md` §7.
4. **Docs suggestions are read-only** — the Docs API has **no accept/reject endpoint** (proven by full API enumeration) and exposes no suggestion author. Accept/reject is a future `PlaywrightBackend` concern. See `research/docs-suggestions-reference.md`.
5. **`Backend` seam:** API-first, with UI-automation (`PlaywrightBackend`) reserved for the genuinely API-impossible ops (accept/reject suggestion, true cell-anchored comment). `ApiBackend` raises `UnsupportedOperation` for those today.
6. **Writes are ON by default**, gated by `read_only` (which also narrows to `.readonly` OAuth scopes). **Caching is OFF by default** (the tool is used in live multi-reviewer sessions where a self-only-invalidated cache goes stale). No persistent storage of comment content.
7. **Three entry points:** `Workspace.from_credentials(creds)` (BYOD), `Workspace(backend=…)` (DI / run-as-a-service), `Workspace.from_oauth(...)` (interactive login → delegates to `from_credentials`).

## Commands

```bash
pip install -e ".[dev]"        # install (src/ layout, Python >=3.10)
pytest -q                       # unit suite — no network, no credentials (uses FakeBackend)
# Live integration suite (real Google; opt-in only):
CSA_GW_INTEGRATION=1 CSA_GW_CLIENT_SECRETS=path/to/client_secret.json pytest tests/integration/
```

## Working in this repo

- **Branch + PR for every change** (never commit to `main`); merge when CI is green.
- **CI is GitHub CodeQL default-setup + a Python analyze job** (no workflow files in-repo). Two gotchas seen: CodeQL flags `"host" in url`-style substring checks (`py/incomplete-url-substring-sanitization`) even in test assertions; and an OAuth **scope grant ≠ API enablement** — a scoped token still 403s `SERVICE_DISABLED` until each API (Docs/Sheets/Slides) is enabled in the Cloud project.
- **New phases follow the plan-then-execute rhythm:** write a spec/plan under `docs/superpowers/`, then implement TDD (unit tests via `FakeBackend`). Keep `README.md`'s manifest in sync.
- OAuth secrets (`credentials.json`, `token*.json`) and probe transcripts are gitignored — never commit them.

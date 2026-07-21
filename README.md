# csa-google-workspace

A **Python library** for managing **comments** — and, in progress, **content** — on Google **Docs, Sheets, and Slides**, via the Google APIs. Comments are handled uniformly across all three file types (they're a single Drive API v3 concern); content read/write is being added phase by phase.

> **Status:** under active, phased development. **Comments are shipped** (open a file → list/filter/reply/resolve/reopen/edit/soft-delete). Content read/write, Sheets cell-mapping, and reading Docs suggestions are planned — see [`docs/superpowers/plans/`](./docs/superpowers/plans/). Design & API-behavior research are complete; see [`CHANGELOG.md`](./CHANGELOG.md).

## Install & test

```bash
pip install -e ".[dev]"     # src/ layout, Python >=3.10
pytest -q                    # unit suite: no network, no credentials
```

## Usage

```python
from csa_google_workspace import Workspace

ws = Workspace.from_credentials(my_google_creds)   # BYO credentials (or .from_oauth("client_secret.json"))
doc = ws.open("https://docs.google.com/document/d/…/edit")   # -> Doc | Sheet | Slides

for c in doc.comments.filter(resolved=False):      # triage open comments (any file type)
    print(c.author.display_name, c.content)
    c.reply("looking into it")
    c.resolve()

doc.create_comment("Please review section 3")
```

Entry points: `Workspace.from_credentials(creds)` (bring-your-own credentials), `Workspace(backend=…)` (dependency injection / run-as-a-service), `Workspace.from_oauth(...)` (interactive login). Writes are on by default; pass `read_only=True` to lock them (and narrow to read-only OAuth scopes).

## Documents

| Document | What it is |
|----------|------------|
| [`docs/superpowers/specs/2026-07-20-csa-google-workspace-design.md`](./docs/superpowers/specs/2026-07-20-csa-google-workspace-design.md) | **The design spec.** Scope, two-axis architecture, API surface, error model, phasing. |
| [`docs/superpowers/plans/`](./docs/superpowers/plans/) | Phased, TDD implementation plans (foundations, comments, …). |
| [`research/google-drive-comments-reference.md`](./research/google-drive-comments-reference.md) | Canonical reference on how Drive/Sheets comments actually work: the 10 API methods, fields, resolution/deletion models, OAuth scopes, and the hard truth about the `anchor` field. |
| [`research/docs-suggestions-reference.md`](./research/docs-suggestions-reference.md) | How Docs **suggestions** behave: readable (incl. accepted/rejected previews), but **no accept/reject endpoint** and no author exposed. |
| [`research/server-landscape.md`](./research/server-landscape.md) | Source-verified survey of prior-art servers that handle Google comments. |
| [`research/mcp-server-design.md`](./research/mcp-server-design.md) · [`research/mcp-protocol-notes.md`](./research/mcp-protocol-notes.md) | Earlier MCP-server design + protocol notes (kept for reference should an MCP wrapper be added). |
| [`experiments/`](./experiments/) | Runnable **empirical probes** (with dated `RESULTS.md`): `anchor-probe`, `comment-lifecycle`, `docs-suggestions`. Probe beats docs. |
| [`CHANGELOG.md`](./CHANGELOG.md) | What changed in each refresh, and why. |

## Three things worth knowing

1. **Comments are a Google Drive API v3 concern — not the Sheets/Docs/Slides APIs** (those handle content). One comment API serves all three file types. (Sheets *notes* are separate and out of scope.)
2. **You cannot anchor a comment to a specific Sheets cell via the API.** Google treats API-created anchors as unanchored; the real anchor is a `workbook-range` with an opaque id. Mapping a comment back to a cell requires exporting the sheet as XLSX and parsing the comment XML — the central hard problem, slated for a later phase.
3. **The space isn't greenfield, so the value is in the hard parts** — reliable read-side cell mapping and clean Docs/Sheets/Slides coverage — not merely "supporting comments." See [`server-landscape.md`](./research/server-landscape.md).

## License

Dual-licensed under [MIT](./LICENSE-MIT) and [Apache 2.0](./LICENSE-APACHE).

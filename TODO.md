# TODO / backlog

The feature roadmap (comments · content read/write · Sheets cell-mapping · Docs
suggestions read) is **complete and live-verified** — see `CHANGELOG.md`. This file
is the post-roadmap backlog: enhancements and polish, none of them blocking, all
kept inside the library's scope (comments + content on Google Docs/Sheets/Slides).

Ordered by leverage-to-effort. Nothing here is committed to — it's a menu. Each item,
when picked up, follows the plan-then-execute rhythm (spec/plan under
`docs/superpowers/`, then TDD via `FakeBackend`). The dense per-phase execution ledger
lives in `.superpowers/sdd/progress.md`; this file is the human-facing view.

## Tier 1 — make the "embeddable, typed" promise real (small, high leverage)

- [ ] **`py.typed` marker (PEP 561).** The source is fully type-hinted, but there's no
  marker + `package-data` entry, so a downstream MCP/plugin author's `mypy`/`pyright`
  treats `csa_google_workspace` as *untyped*. Directly undercuts the "clean, typed
  surface" positioning in the README. ~10 lines.
- [ ] **Package metadata.** `pyproject.toml` has no `readme`, `license`/license-files,
  `classifiers`, `keywords`, `[project.urls]` (repo, issues), or `authors`. It's
  `0.0.1` with no PyPI-facing identity. Add these; decide on a first tagged release.
- [ ] **CI that runs the test suite.** CI today is CodeQL default-setup + a Python
  *analyze* job — the 146 unit tests (which guard every probe-verified Google quirk)
  **never run on a PR**. Add a small GitHub Actions workflow: `pytest` across
  Python 3.10–3.13.

## Tier 2 — formalize the guarantees (small–medium)

- [ ] **ruff (lint + format) + mypy (or pyright)** in dev deps and CI — turns "typed"
  from aspiration into an enforced gate; would have caught boundary bugs like the
  ones the slow-sweep audit found.
- [ ] **Coverage reporting** (`pytest-cov`) — strong test suite already exists; measure it.

## Tier 3 — real API-surface gaps (within scope)

- [ ] **Sheets `append_rows`** (`spreadsheets.values.append`) — the common Sheets write
  op that's missing; today only `update`/`clear`/`batch_update` exist. Automation/review
  bots append log rows constantly.
- [ ] **Slides write symmetry.** Slides exposes only `replace_text` + raw `batch_update`,
  while Docs has `insert_text`/`append_text`/`delete_range`. Decide whether per-slide
  text/notes writes belong, or whether the asymmetry is intentional.
- [ ] **`Sheet.as_text()` renders only the first tab** (`sheet.py`) — multi-tab sheets
  silently lose data. Add a `tab=` param and/or render all tabs.

### Tier 3 minor / polish (small, tracked in `progress.md`)

- [ ] `replace_text` discards `occurrencesChanged` → a no-match is indistinguishable
  from a match (Doc + Slides).
- [ ] `Sheet.batch_update` can stale the cell-map cache (raw escape hatch).
- [ ] `Doc.suggestions` type hint / minor docstring drift.

## Tier 4 — prove the pitch (scope-adjacent)

- [ ] **`examples/` reference consumer** — a small MCP server or comment-triage bot built
  on the library. Most direct proof of the "embed in MCP/plugins" positioning, and it
  surfaces real ergonomics (auth injection, async). Stays out of the *core* per the design.
- [ ] **Async story — decide.** MCP servers/bots are usually async; sync-only forces
  `asyncio.to_thread`. Lean: *document the `to_thread` pattern* (cheap) rather than build
  an async facade (large, and `google-api-python-client` is sync). Just needs a call.

## Deferred — bigger / genuinely out of reach today (already tracked)

These are recorded design decisions, **not bugs**:

- [ ] **`Location.tab` resolution** — multi-tab cell disambiguation via `workbook.xml` +
  rels (part → sheet-name). Real correctness gap for multi-tab sheets; its own task.
- [ ] **Caching pass** — accessors re-fetch per call by design (the tool is used in live
  multi-reviewer sessions where a self-only-invalidated cache goes stale). An *opt-in* /
  request-scoped cache is the biggest runtime win for embedded review sessions.
- [ ] **10 MB XLSX export cap** — large sheets silently degrade the cell-map; accepted
  today (no logging infra to surface it).
- [ ] **Accept/reject suggestions & true cell-anchored comment creation** — API-impossible
  (proven by probe); reserved for a future `PlaywrightBackend`. `ApiBackend` raises
  `UnsupportedOperation`.

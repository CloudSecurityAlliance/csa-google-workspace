# TODO / backlog

The feature roadmap (comments · content read/write · Sheets cell-mapping · Docs
suggestions read) is **complete and live-verified** — see `CHANGELOG.md`. This file
is the post-roadmap backlog: enhancements and polish, none of them blocking, all
kept inside the library's scope (comments + content on Google Docs/Sheets/Slides).

Ordered by leverage-to-effort. Nothing here is committed to — it's a menu. Each item,
when picked up, follows the plan-then-execute rhythm (spec/plan under
`docs/superpowers/`, then TDD via `FakeBackend`). The dense per-phase execution ledger
lives in `.superpowers/sdd/progress.md`; this file is the human-facing view.

## Near-term objective: audit → cleanup → PyPI

The agreed next milestone is to **audit the library, clean up what the audit finds, and
publish it to PyPI.** The correctness findings in Tier 0 below and the release-readiness
work in Tier 1 are the substance of that milestone; Tier 2 tooling supports it. Treat
these three tiers as the "1.0-on-PyPI" work-package.

**Progress (2026-07-21):** Tier 0 fixes (PR #26), `py.typed` (PR #27), pytest CI (PR #28),
and the package-metadata pass are all done — the package builds and `twine check` passes
for sdist + wheel at **v0.1.0**. **The only step left to actually publish is the release
itself** (tag + upload), which needs a decision + a PyPI token — see "Publish" below.
Tier 2 tooling (ruff/mypy/coverage) is optional polish, not a publish blocker.

### Publish (the actual release — needs a human decision + credentials)

- [ ] **Cut v0.1.0.** Tag the release and upload. Two paths:
  (a) manual — `python -m build` then `twine upload dist/*` with a PyPI API token; or
  (b) **preferred** — configure PyPI **Trusted Publishing** (OIDC) + a
  `release`-triggered GitHub Actions job, so no long-lived token is stored. Requires
  registering the project on PyPI first. (Optionally publish to TestPyPI once as a dry run.)

## Tier 0 — audit findings (correctness) — ✅ DONE

Confirmed by an external review (2026-07-21), re-verified against the code, and fixed:

- [x] **`Workspace.open()` leaks a raw `HttpError`.** ✅ Fixed in PR #26. `ApiBackend.get_file_metadata`
  (`backend.py:190`) is the *only* data method that calls `.execute()` without
  `_errors.call(...)`, so the first call a consumer makes raises a raw
  `googleapiclient.errors.HttpError` on a missing/forbidden/service-disabled file
  instead of the typed `NotFoundError`/`PermissionError`/`ServiceDisabledError` the spec
  promises. **Fix:** wrap in `_errors.call`, **and** add an `ApiBackend`-level test that
  feeds a stub service raising `HttpError` and asserts typed translation — no
  `FakeBackend` test can catch this class of bug, because the fake raises typed errors
  directly (the one blind spot of the fake/real seam).
- [x] **Cell-map degrade is spec-noncompliant (no recorded warning).** ✅ Fixed in PR #26
  (stdlib `logging` WARNING on degrade; genuine no-match stays quiet). The spec
  (`docs/superpowers/specs/2026-07-20-csa-google-workspace-design.md:334`) requires
  `_cellmap` to degrade to `location=None` **plus a recorded warning**. `sheet.py:63`
  does the `location=None` half but records nothing, so export-cap-exceeded,
  access-denied, malformed XLSX, and genuine no-match are indistinguishable to callers.
  Shares a root cause with the tracked "10 MB export cap silently degrades" item:
  **there is no logging/warnings story.** **Fix (shared, minimal):** adopt stdlib
  `logging` + `warnings.warn`; closes both. Resist anything heavier.

## Tier 1 — make the "embeddable, typed" promise real (small, high leverage)

Both items below were independently flagged by the same external review — good signal
they're the right release-readiness priorities.

- [x] **`py.typed` marker (PEP 561).** ✅ Shipped in PR #27 (marker + `package-data`;
  verified present in a built wheel + a packaging test guards it).
- [x] **Package metadata.** ✅ Done: `readme`, SPDX `license = "Apache-2.0"` +
  `license-files`, `authors`/`maintainers`, `keywords`, trove `classifiers`
  (incl. `Typing :: Typed`), `[project.urls]`, and a single-sourced dynamic version.
  Bumped to `0.1.0`; `build` + `twine check` green for sdist + wheel.
- [x] **CI that runs the test suite.** ✅ Added in PR #28 — GitHub Actions runs
  `pytest -q` across Python 3.10–3.13 on push + PR (offline; live suite stays gated).

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
- [x] **10 MB XLSX export cap** — large sheets degrade the cell-map. ✅ No longer *silent*
  as of PR #26: the shared logging story records a WARNING naming the cause. (Raising the
  cap itself is still out of reach — it's a Google export limit.)
- [ ] **Accept/reject suggestions & true cell-anchored comment creation** — API-impossible
  (proven by probe); reserved for a future `PlaywrightBackend`. `ApiBackend` raises
  `UnsupportedOperation`.

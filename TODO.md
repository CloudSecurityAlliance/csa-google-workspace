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

### Publish — ✅ DONE

- [x] **Release automation** — `.github/workflows/release.yml` (Trusted Publishing / OIDC);
  steps in `RELEASING.md`.
- [x] **Published to PyPI** — `0.1.0` and `0.1.1` (docs patch) both cut via `gh release
  create` → CI-built, tagged, GitHub-Released, uploaded over OIDC. Page:
  <https://pypi.org/project/csa-google-workspace/>.

## Release-process / supply-chain hardening

From a 2026-07-23 release-process review (re-verified here). Worst-first. Marked
**🔧 code/config** (a PR does it) or **⚙️ admin** (needs GitHub/PyPI settings + a decision).

- [ ] **⚙️ Protect `main` (highest — the real trust boundary).** `main` is unprotected
  (verified: `404 Branch not protected`), so the lint/test/security/CodeQL jobs are advisory
  and anything with write access can push straight to `main` — which is what `release.yml`
  builds from. Require PRs + those status checks, block direct push + force-push, enforce for
  admins. Decide the review requirement (mandatory PR *review* changes the current solo/AI
  merge flow — needs a reviewer or an admin bypass).
- [ ] **🔧 Pin GitHub Actions to full commit SHAs.** `release.yml` uses
  `pypa/gh-action-pypi-publish@release/v1` (a mutable branch) on the job holding
  `id-token: write`, plus `actions/checkout@v4` / `setup-python@v5`; `tests.yml` likewise.
  Pin each to a SHA (version in a comment). Highest-value CI hardening — a hijacked ref on the
  publish job could exfiltrate the OIDC token and publish as us.
- [ ] **🔧+⚙️ Environment gate on publish.** Add a protected `pypi` GitHub Environment
  (required reviewer, restrict to `main`), set `environment: pypi` on the publish job, and
  scope the PyPI trusted-publisher binding to that environment → a human approval before any
  upload. (We deliberately omitted this for the first release; add it now.)
- [ ] **🔧 Emit + verify PEP 740 attestations.** Verified gap: **neither `0.1.0` nor `0.1.1`
  carries provenance on PyPI** (`provenance=False`), so attestations aren't landing. Set
  `attestations: true` explicitly on `gh-action-pypi-publish` (and pin it) and confirm the
  next release shows provenance. *Correction to the review's #4:* `0.1.0` is **not**
  orphaned/manual — it's a CI-built, tagged, GitHub-Released artifact (same path as `0.1.1`);
  **do not yank it.** Attestations can't be retrofitted to any existing version, so the fix is
  purely forward-looking.
- [ ] **🔧 Run the security gate at release time.** `release.yml` runs only `pytest` before
  publish, not `pip-audit`/`bandit` — a CVE disclosed after the last PR could ship. Add the
  security steps to the release job (or rely on `security` being a required check via branch
  protection).
- [ ] **🔧 Dependency automation + reproducible build.** Add `.github/dependabot.yml`
  (`pip` + `github-actions` ecosystems). Pin the release build toolchain (`build`, `twine`).
  (A full CI lockfile is optional/heavier for a library.)
- [ ] **🔧 Lower-priority polish.** A "no secrets / expected contents in dist" check
  (`check-manifest` or a grep of the sdist for `research/`/`experiments/` transcripts); fix the
  truncated disclosure line in `SECURITY.md` (add the real maintainer email or drop the dangling
  clause); optional SBOM; a post-publish "install from PyPI + import" smoke step.

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

## Tier 2 — formalize the guarantees — ✅ DONE

- [x] **ruff + mypy in dev deps and CI.** ✅ ruff (lint; E/F/W/I/B/UP, ignoring the
  deliberate `E702` semicolon style, no auto-formatter) + mypy (`check_untyped_defs`,
  google stack marked untyped) now run as a dedicated `lint` CI job. Fixed the findings
  (mostly test cleanups + typing the injected `_backend`/`_file_id` fields and the
  `CommentsMixin` attributes).
- [x] **Coverage reporting** (`pytest-cov`). ✅ Wired into the CI matrix with
  `fail_under = 85` (total ~87%; the shortfall is the integration-only ApiBackend +
  interactive OAuth paths).

## Tier 3 — real API-surface gaps — ✅ DONE

- [x] **Sheets `append_rows`** (`spreadsheets.values.append`, `INSERT_ROWS`). ✅ Added;
  non-idempotent so never auto-retried on 5xx.
- [x] **Slides write symmetry.** ✅ Added `Slides.insert_text(object_id, text, index=0)`
  (shape-addressed, symmetric to `Doc.insert_text`) + `Slide.shape_ids` to discover
  targetable shapes. Decision: a fuller shape model (bulk shape CRUD) stays out — raw
  `batch_update` remains the escape hatch; the asymmetry with Docs is inherent (Slides is
  shape-addressed, Docs is a linear index).
- [x] **`Sheet.as_text(tab=…)`** ✅ now renders **all** tabs by default (each with a
  `# <tab>` header when >1), fixing the silent first-tab-only data loss; `tab=` selects one.

### Tier 3 minor / polish — ✅ already resolved (verified in code)

- [x] `replace_text` returns `occurrencesChanged` + `match_case` kwarg (Doc + Slides) —
  fixed in an earlier batch; a no-match (`0`) is distinguishable from a match.
- [x] `Sheet.batch_update` invalidates the cell-map cache (`self._cell_map_cache = None`).
- [x] `Doc.suggestions` is typed `list[Suggestion]`.

## Tier 4 — prove the pitch (scope-adjacent)

- [ ] **`examples/` reference consumer** — a small MCP server or comment-triage bot built
  on the library. Most direct proof of the "embed in MCP/plugins" positioning, and it
  surfaces real ergonomics (auth injection, async). Stays out of the *core* per the design.
- [ ] **Async story — decide.** MCP servers/bots are usually async; sync-only forces
  `asyncio.to_thread`. Lean: *document the `to_thread` pattern* (cheap) rather than build
  an async facade (large, and `google-api-python-client` is sync). Just needs a call.

## Integration / live testing

Three tiers:

- **unit** — `tests/`, offline (`FakeBackend`), 169 tests; gates every PR.
- **integration** — `tests/integration/`, real Google API, opt-in via `CSA_GW_INTEGRATION=1`
  (needs a cached token or a first-run browser login). Covers the full surface incl. Tier 3.
- **oauth** — `tests/oauth/`, the **interactive browser-login** suite (real `from_oauth`,
  token-file permissions, `read_only` contract). **Separate** because it needs a human at a
  browser and touches the very sensitive cached token; own gate `CSA_GW_OAUTH=1`.

```
CSA_GW_INTEGRATION=1 CSA_GW_CLIENT_SECRETS=path/to/client_secret.json pytest tests/integration/
CSA_GW_OAUTH=1       CSA_GW_CLIENT_SECRETS=path/to/client_secret.json pytest tests/oauth/
```

- [ ] **Optional: a manual `workflow_dispatch` CI job** running the live suite with a stored
  Google credentials secret. **Deferred to the security audit** — putting Google creds in CI
  is a threat-model decision, not a default.

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

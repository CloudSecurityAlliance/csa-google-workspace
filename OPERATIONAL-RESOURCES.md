# Operational Resources

Recurring operational work in this project. Mandatory once such work exists; this repository has the
most in the CSA MCP fleet.

**Last reviewed:** 2026-09-16

## Weekly controls check — `controls.yml`

- **What it does** — verifies the security controls that live *outside* the repository still hold
  (repository settings, branch protection, the release path), so a control silently removed in the
  GitHub UI is noticed.
- **Tier** `reliable-scheduled` · **Status** `production` · **Code** `.github/workflows/controls.yml`
- **Serves** — the "controls exist and are enforced" claim in `SECURITY.md` and the threat model.
- **Reads from** GitHub repository settings · **Writes to** the workflow run log
- **Health check** — a run that exits 0 is not by itself evidence; the detector previously always
  exited 0, and the ability to fail on `UNVERIFIABLE` has been a tracked defect.
- **Next review** 2026-12-16

## Doc-claims check — `doc-claims.yml`

- **What it does** — asserts documented claims against the artifacts they describe, so prose that
  disagrees with the code fails rather than drifts. Roughly 25 claims today.
- **Tier** `triggered` · **Status** `production` · **Code** `.github/workflows/doc-claims.yml`
- **Serves** — the failure mode this project has actually suffered: two stale README claims found on
  2026-08-27, one describing a capability that had shipped **fifteen releases earlier**.
- **Known limit** — it checks our docs against *our* code. It cannot catch a claim about **Google's**
  API going stale, which is the other half and is unwatched.
- **Next review** 2026-12-16

## Dependency relock — `relock.yml` · auto-merge — `dependabot-auto-merge.yml`

- **What they do** — keep the hash-pinned dependency closure current, and merge routine dependency
  bumps without a human.
- **Tier** `simple-scheduled` / `triggered` · **Status** `production`
- **Serves** — the supply-chain posture in `PUBLIC-GITHUB-REPO-STANDARDS.md`.
- **Health check** — "lockfiles are behind the current resolution" has been filed twice (#334, #442),
  so drift here is recurrent rather than theoretical.
- **Next review** 2026-12-16

## Release — `release.yml`

- **What it does** — builds and publishes to PyPI via Trusted Publishing with attestations.
- **Tier** `triggered` · **Status** `production` · **Cadence** high — 77 releases since 2026-07-23
- **Serves** — the "always newer than most software you install" claim in the README, which is a
  deliberate posture rather than an accident.
- **Next review** 2026-12-16

## Tests — `tests.yml`

- **What it does** — the unit and conformance suites.
- **Tier** `triggered` · **Status** `production`
- **Known limit, and it is serious** — **CI is ubuntu-only.** The suite has 27 Windows failures
  (#453), and that gap is how three named security mitigations turned out to be POSIX-only no-ops
  (#452). A green CI badge currently means "green on one platform".
- **Next review** 2026-12-16

## Gaps

- **Nothing watches Google's API surface for drift** —
  [CINO-PE #49](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/issues/49).
  The Docs API gained comments and suggestion accept/reject in Developer Preview, obsoleting two of
  this project's own "API-impossible" claims, and **a human noticed**. GA is expected 2027-01.
- **No Windows or macOS CI**, per the limit above.

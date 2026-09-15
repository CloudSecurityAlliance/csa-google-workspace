# Security audit records

One directory per audit. Each records what was examined, by what, under what
conditions, and what was found — including what was looked for and *not* found,
and what was rescored or withdrawn along the way.

The **living** documents are elsewhere and are what to read first:

- [`SECURITY.md`](../../SECURITY.md) — the standing threat framing and the
  division of responsibility between this library and its embedders.
- [`THREAT_MODEL.md`](../../THREAT_MODEL.md) at the repository root — the living
  threat model, **adopted 2026-08-28** from audit `2026-08-27-01` (#197). Its
  threat text is as that audit wrote it; its `status` column is current, and §0
  accounts for every row that has moved since. Each audit directory keeps the
  model as that audit produced it — the frozen snapshot behind its findings — and
  an audit **proposes** changes to the living model by filing an issue rather than
  editing the root file, so parallel audits cannot collide over it. The 2026-08-27
  snapshot is [here](2026-08-27-defending-code-reference-harness-claude/THREAT_MODEL.md).

Structure, naming, front-matter schema and conventions: [`SCHEMA.md`](SCHEMA.md).

---

## Index

Newest first.

<!-- BEGIN GENERATED INDEX -->
| audit | date | tool | model | interaction | automation | depth | findings | remediation |
|---|---|---|---|---|---|---|---|---|
| [2026-09-01 · ChatGPT Codex / GPT-5](2026-09-01-chatgpt-codex-gpt5/) | 2026-09-01 | codex + chatgpt-codex-local-repository | gpt-5 | light | assisted | standard | 3 total · 0 exploitable · 2 hardening | complete — see [REMEDIATION.md](2026-09-01-chatgpt-codex-gpt5/REMEDIATION.md); threat-model rows deferred by decision |
| [2026-09-01 · defending-code-reference-harness / claude (re-audit)](2026-09-01-defending-code-reference-harness-claude/) | 2026-09-01 | claude-code + anthropics/defending-code-reference-harness | claude-opus-5 | heavy | assisted | adversarial | 43 threats · 9 flaws · 10 guards-that-cannot-fail · 1 refuted · 1 fixed upstream mid-audit | not started — 25 issues filed (#308-#332); #1 was already fixed upstream by #305. Fixing deferred to a separate session |
| [2026-08-27 · defending-code-reference-harness / claude](2026-08-27-defending-code-reference-harness-claude/) | 2026-08-27 | claude-code + anthropics/defending-code-reference-harness | claude-opus-5 | heavy | assisted | adversarial | 35 total · 1 exploitable · 15 hardening | in progress — see [REMEDIATION.md](2026-08-27-defending-code-reference-harness-claude/REMEDIATION.md) |
| [2026-07-22 · Code audit, security-lensed](../AUDIT-2026-07-22.md) † | 2026-07-22 | claude-code | — | moderate | assisted | standard | 29 (#1…#29) | findings-only |
| [2026-07-22 · Security audit](../SECURITY-AUDIT-2026-07-22.md) † | 2026-07-22 | claude-code + pip-audit, bandit, defusedxml fuzzing | — | moderate | assisted | standard | 4 (SEC-1…SEC-4) | findings-only |
<!-- END GENERATED INDEX -->

† Predates this directory and still lives in `docs/`, because `SECURITY.md`
references those paths. Migrating them into `2026-07-22-claude-code/` means
updating that reference — filed as an issue rather than done here.

---

## Coverage and staleness

The most useful thing this index can tell you is **which audit covered which
code**. Both 2026-07-22 audits cover **v0.1.0 — 1,308 LOC across 15 modules**.
At v0.28.0 the tree is ~8,500 LOC across 53 modules, and everything implementing
the read-to-act path was written afterwards. That gap was invisible until it was
looked for, which is the reason this table exists.

<!-- BEGIN GENERATED COVERAGE -->
| group | first covered by |
|---|---|
| `src/csa_google_workspace/` — top level | **partial** — 22/25 at 2026-09-01 · 77% of lines |
| `documents/` — per-type content | 2026-07-22 · claude-code |
| `mcp/` — server, auth flow, config, resources | **partial** — 15/16 at 2026-09-01 · 84% of lines |
| `mcp/_tools/` — the tool registrations | 2026-08-27 · claude-code · 58% of lines |
| `demo/` | 2026-08-27 · claude-code · 84% of lines |
| `tests/` as code | **partial** — 13/137 at 2026-09-01 · 15% of lines |
| `.github/workflows/` | 2026-09-01 · codex · 94% of lines |
| packaging and secret-scanning config | 2026-08-27 · claude-code · 83% of lines |
| `scripts/` | **partial** — 6/7 at 2026-09-01 · 76% of lines |
| `experiments/` | **not yet audited** |
| `research/` | **not yet audited** |
<!-- END GENERATED COVERAGE -->

**Both tables above are generated** by `scripts/gen_audit_index.py` from each audit's
front matter, and CI fails if the committed copy has drifted. Do not edit them by hand.

Coverage is **computed against the tracked tree**, not restated: each audit declares
`modules_covered` as globs, and a group counts as covered only when an audit's globs match
*every* tracked file in it. Partial coverage says so, with the count. A group no audit matches
reads **not yet audited** — so a newly-added module surfaces as uncovered by itself, rather
than when somebody thinks to look. That is the failure being fixed: not a stale table, but a
coverage claim that reads as broader than it is.



## What an audit may commit

**An audit commits only its own directory.** Nothing else — not `SECURITY.md`,
not the root `THREAT_MODEL.md`, not a README typo it noticed in passing, and not
a source fix however small. Everything outside the audit directory is written up
and **filed as an issue**, including proposed updates to the living threat model.

Two reasons, and the second is the load-bearing one:

1. It keeps the flaw trail and the fix trail separate, so both stay
   independently reviewable.
2. **It lets audits run in parallel.** Several audit agents can work the same
   commit at once — different tools, different scopes — and never touch a shared
   file, so none can conflict with another or with whoever is applying fixes.
   That property disappears the moment an audit is allowed to edit a document
   outside its own directory.

**There is no longer an exception.** This index used to be one — every audit had to add its
row and update the coverage table — and it was the last shared mutable file in a workflow built
so that parallel audits never touch one. Both tables are now generated from per-audit front
matter (#198), so an audit writes its own directory and nothing else. `SCHEMA.md` changes only
when the schema does, which is not something an audit does in passing.

## Why fixes are not made in the audit context

Findings are recorded here and remediated elsewhere, deliberately. The audit
directory carries the flaw and the reasoning that produced it; `REMEDIATION.md`
in the same directory carries the fix and the reasoning that produced *that*,
written in a different session. Separating them keeps both independently
reviewable, and stops a fix from quietly reshaping the description of the
problem it was written against.

## Auditing the same commit with a different tool

Encouraged, and the reason the tool name is in the directory name. Two audits of
`95c6afa` by different tools are directly comparable, and the interesting
output is the disagreement: what one found and the other missed, and where they
rated the same finding differently. The `confidence: refuted` entries in
§7 of an existing record are the cheapest thing a second audit can inherit —
they say where not to spend effort.

Worth knowing before running a second audit of this commit: the 2026-08-27
record's §7 clears eleven items with reasons, including openpyxl's automatic
`defusedxml` routing, the non-applicability of the `mcp` SDK's HTTP-transport
advisories to a stdio-only server, and the absence of any SSRF path. Its §6
records three ratings that were withdrawn or changed during the audit, which is
the calibration a comparing reader needs.

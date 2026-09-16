# Goals

Inferred from what this project has actually built, fixed and refused — 116 issues, 76 releases in seven weeks,
two dated security audits (`audit-2026-07-22`, `audit:2026-08-27-01`) — rather than from ambition. If a goal here is not visible in the tracker
or the changelog, it does not belong.

Shared goals for CSA's MCP server fleet — library-first, local stdio, one fail-closed seam at the
data boundary, capability coverage over API coverage — are stated once in the fleet roster
(`surfaces/mcp/ROSTER.md` in the internal CINO-Platform-Engineering repo) and are not restated here.
This file records only what is specific to Google Workspace.

## North Star

A person can point this at their own Drive, in their own AI client, and trust it with documents that
matter — because every claim it makes about Google's behaviour has been **probed rather than
inferred**, and every capability it does not have is stated rather than hidden.

**Correction, 2026-09-16.** This file previously said the differentiator was *comments*. A capture of
Google's own four Workspace MCP servers ([`research/captures/`](research/captures/)) falsified that:
`docsmcp` and `sheetsmcp` **write** comments and `docsmcp` **accepts and rejects suggestions**, and all
four read comments. That is [#364](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/364)
having already shipped while nothing here was watching.

What survives the capture, stated narrowly because the broad version was wrong:

- **Slides comment writes** — Google reads them and does not write them.
- **Sharing writes** — Google has `get_file_permissions` and nothing that grants, revokes, or resolves
  an access proposal.
- **The capability layer** — Google's servers have no profiles, no gating, and no operator control over
  what an agent may do. That is the whole of this project's security posture, and it is the
  differentiator that does not evaporate when a vendor ships a feature.
- **Anchors** — plausibly, and *not established*. It needs a behavioural comparison rather than a
  registry diff.

The durable position is therefore **not** a capability nobody else has. It is that this server can be
pointed at a real person's Drive and constrained, which is a different claim and a harder one to
obsolete ([#340](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/340) — people
arrive having already failed to build this themselves).

## Near-term

| Goal | Success metric |
|---|---|
| **Cross-platform honesty** | The unit and conformance suites pass on Windows and macOS, and CI runs both. Today CI is ubuntu-only and the suite has 27 Windows failures ([#453](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/453)) — which is how three named security mitigations turned out to be no-ops there ([#452](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/452)) |
| **Every behavioural claim is probed** | No statement about Google's behaviour rests on inference. An unprobed claim is filed as a defect, as Slides comments were ([#400](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/400)) |
| **The tool surface does not break its consumers** | No tool rename, no silently widened vocabulary. `context_kind` growing without warning ([#422](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/422)) is the shape to avoid; consumer-reported inconsistency ([#421](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/421)) is the signal that works |
| **Guards can fail** | Every guard has a test that proves it fires — demonstrated by breaking it. Three guards from a prior remediation were found asserting nothing ([#320](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/320)), alongside a drift detector that always exited 0 ([#316](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/316)) and a conformance test that was asymmetric ([#325](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/325)) |
| **Read-only is refused upstream, not by us** | The read-only guarantee is proven by Google declining the call, not by our own gate ([#443](https://github.com/CloudSecurityAlliance/csa-google-workspace/pull/443)) |

## Medium-term

- **A public reference corpus** — real files, permanently available, serving three jobs at once:
  the documented example set, a regression canary against Google changing behaviour, and the fixture
  set for native-API work ([#388](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/388)).
  Probing currently depends on private documents, which is why some claims are unverifiable by anyone else.
- **Close the capability gaps that have a known upstream route** — past revisions
  ([#389](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/389)), Drive's approvals
  resource ([#413](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/413)), comments
  surviving `copy_file` ([#339](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/339)),
  Slides anchors we currently resolve and discard ([#427](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/427)).
- **Prompt injection treated as a first-class surface, not a footnote.** Document content is
  attacker-controlled and is rendered to the model as the document's own words
  ([#380](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/380)). Research what
  scanning actually buys before adopting any of it ([#297](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/297)).
- **Security controls readable in one place, with a guided setup** ([#286](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/286)).
  The controls exist; nobody can currently find them all.

## Long-term

- **1.0.0 when the tool surface stops moving** — not on a date. Until then `0.N+1.0` keeps shipping.
- **A hosted deployment.** Wanted, and a large piece of work. It is the one change that would alter
  whose credential this acts with, which is the thing that currently forces local stdio.
- **The post-refactor differential benchmark** — ~18 AI security-audit tools measured against a
  codebase whose real findings are known, published as a CSA report
  ([#113](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/113)). This repo is
  unusually well suited to it because two audit campaigns are already recorded with outcomes.

## Non-goals

Named so they are decisions rather than drift.

- **Feature parity with the other Drive MCP servers.** Explicitly abandoned as a framing — the
  question is what a person needs done, not what a competitor's tool list contains.
- **A 1.0.0 milestone by calendar date.** Freezing a surface still moving daily would make the
  stability promise a lie.
- **Write access as a default.** Destructive tools ship present-and-off; having a tool and being
  permitted to call it are separable.
- **Being the source of truth for anything.** Google holds the documents. This reads and writes
  through the vendor's API and stores nothing.

## How we would know this failed

The failures most likely to go unnoticed, in order of likelihood:

1. **The docs drift ahead of or behind the code and nobody notices.** Already happened — two stale
   claims in the README on 2026-08-27, one describing a capability that had shipped *fifteen releases
   earlier*. The mitigation is a test, not vigilance.
2. **A guard that no longer asserts anything still passes.** Already happened — three from one remediation, plus a drift detector that always exited 0. Guards
   decay silently and a green suite is not evidence.
3. **Someone's own build failed, so they do not believe this one works.** The trust failure is
   upstream of any feature ([#340](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/340)).
4. **A security mitigation is real on the maintainer's platform and a no-op elsewhere.** Already
   happened on Windows, three at once, and the threat model said otherwise.

## Who benefits

- **CSA** — document review, comment triage and the peer-review register become scriptable.
- **Anyone with a Google Workspace account** — public, PyPI-published, free. Google's own Drive
  server declines the destructive tools; this one ships them off by default, which is a different
  answer to the same question rather than a better one.
- **The fleet** — this is the most-weathered CSA MCP server, so its scar tissue is where the shared
  standard comes from.

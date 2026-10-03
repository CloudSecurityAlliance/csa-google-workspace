# RACI

| Role | Who |
|---|---|
| **Responsible** | Kurt Seifried |
| **Accountable** | Kurt Seifried |
| **Consulted** | CSA staff reviewing documents through the comment workflow — as users, not a standing body |
| **Informed** | Anyone installing the server; `security@cloudsecurityalliance.org` for anything in [`SECURITY.md`](SECURITY.md)'s scope |

One name in the first two rows is accurate rather than a placeholder. Naming a committee that
does not meet reads as answered, which is worse than reading as concentrated.

## What the concentration costs

This repo is unusually well defended against it, and the defences are worth naming because they
are the mitigation:

- **Decisions are written down with their rejected alternatives** — [`docs/DECISIONS.md`](docs/DECISIONS.md).
- **Claims are checked rather than asserted** — `scripts/check_doc_claims.py`,
  `scripts/check_controls.py` and `scripts/check_release_history.py` run on a schedule
  ([`OPERATIONAL-RESOURCES.md`](OPERATIONAL-RESOURCES.md)), so documentation drift fails rather
  than accumulating in one person's memory.
- **The threat model is a file, not a conversation** — [`THREAT_MODEL.md`](THREAT_MODEL.md), and
  `CLAUDE.md` requires an audit to propose a change to it *by filing an issue, never by editing
  the file*. That rule is what makes the model reviewable by someone else later.

What remains genuinely concentrated:

- **Which of the ~29 open findings matter most**, and in what order. `TODO.md` indexes them;
  the ranking is judgement.
- **The Google Cloud projects.** `csa-drive-docs-mcp` is the live client's project. Rotating or
  replacing a client is a Console operation one person currently knows —
  [`BACKUP-RESOURCES.md`](BACKUP-RESOURCES.md) records why that matters and why no backup helps.

## Escalation

- **A security issue** → GitHub Private Vulnerability Reporting, or
  `security@cloudsecurityalliance.org`. [`SECURITY.md`](SECURITY.md) is reachable by an external
  reporter with no CSA access, which is the property that matters for a public repo.
- **Anything else** → an issue on this repo. `report_a_problem` assembles a filable report
  containing no file ids and no credentials, so what happened stays the reporter's to describe.

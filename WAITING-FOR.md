# Waiting for

Blockers with someone else's name on them. Work that is merely unfinished is in
[`TODO.md`](TODO.md); the distinction is whether this project can move it alone.

| Waiting on | What for | Cost of waiting |
|---|---|---|
| **Google** | #364 — the Docs API's comments and suggestion accept/reject are in **Developer Preview**. They obsolete two of this repo's "API-impossible" claims | Those claims are currently true and documented as permanent. When the preview ships they become wrong, and a documented impossibility is the hardest kind of staleness to notice |
| **Google** | #399 — does a Drive-API comment notify anybody? Unknown, and **both answers are operationally serious**: silent comments mean reviewers never see them, notifying comments mean a bulk operation emails everyone | Blocks any confident advice about bulk comment creation |
| **Google** | #413 — Drive v3 has an approvals resource nothing here mentions | A native document-approval workflow may already exist where we would otherwise build one |
| **A decision (Kurt)** | #471 — should Dependabot watch the pip ecosystem at all? Two unsatisfiable PRs in one day | Noise that trains people to ignore Dependabot, which is the opposite of the point |
| **A decision (Kurt)** | CINO-PE#172 — does the Windows job gate coverage, and at what? | This repo's Windows job measures **no** coverage at all, so the `icacls` paths are pragma'd on ubuntu and unmeasured on Windows. The measurement and three options are on that issue |
| **A macOS machine** | #463 — the macOS rig should match the Windows one, starting with its log not being safe to hand over | Platform asymmetry in the diagnostic path, which is where asymmetry is least visible |

## Not waiting on anything

Recorded so nobody looks for a blocker that is already resolved:

- **#495 and #510 are closed.** A retired OAuth client now reports `client_retired` instead of
  `ready`-while-everything-fails. The deleted project cannot come back; the remedy is to replace
  the client, and the server now says so.
- **#452 is fixed** by #451 — `icacls /inheritance:r`, an explicit `islink` refusal, and
  `file_is_owner_only()` replacing the `0o600` literal. What remains open on that issue is a
  `THREAT_MODEL.md` wording choice, which the issue itself calls a reviewer's call. Verified
  working on Windows 2026-10-02: the current credential files report `owner_only=True`, and a
  pre-fix backup reports `False` — see [`BACKUP-RESOURCES.md`](BACKUP-RESOURCES.md).
- **#511 is fixed** — the console script is `.exe` on Windows, so the "beside this interpreter"
  lookup now goes through `shutil.which` and `.resolve()`.

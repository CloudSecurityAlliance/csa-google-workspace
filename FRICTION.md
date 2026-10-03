# Friction

What cost time here, so it costs it once. Bugs go to
[issues](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues); this is for the
friction that recurs because nothing in the repo remembers it. Each entry names its issue.

## F1 — Three named mitigations were no-ops on the platform most users run (#452)

`THREAT_MODEL.md`'s T5 row cited parent directory `0700`, `os.open` with `O_NOFOLLOW`, and a
post-open `fchmod 0600`. Measured on Windows 11 / CPython 3.14:

```
mode after os.open(..., 0o600) : 0o666
mode after os.chmod(0o600)     : 0o666
os.O_NOFOLLOW                  : ABSENT from the os module
```

`os.chmod` on Windows honours only the read-only bit, and `O_NOFOLLOW` was passed as
`getattr(os, "O_NOFOLLOW", 0)` — on Windows that is literally `| 0`, so **the flag reads as
present in the source while the defence is absent.** Nothing caught it because CI was
`ubuntu-latest` only.

The honest statement of the pre-fix position is not *"the token was world-readable"* — it
usually was not — but *"the mitigation T5 cited was not the thing providing the protection."*
NTFS inheritance from the user profile was. That distinction is what the row had to be reworded
to say.

Fixed in #451: `icacls /inheritance:r /grant:r <user>:F`, an explicit `islink` refusal, and
`file_is_owner_only()` replacing the `0o600` literal. **Verified still working 2026-10-02** —
see [`BACKUP-RESOURCES.md`](BACKUP-RESOURCES.md), where a pre-fix backup reports
`owner_only=False` beside current files reporting `True`.

The transferable form: **a mitigation written as a POSIX call is a claim about POSIX.** Assert
the property through an API that reads the thing that actually governs access.

## F2 — `Path.exists()` on a console script is always False on Windows (#511)

The "script beside this interpreter" lookup tested a suffix-less path. The installed file is
`.exe`, so the branch never matched on any Windows machine.

`shutil.which(SCRIPT_NAME, path=...)` plus `.resolve()` is the fix — `.resolve()` because
`which` returns **`PATHEXT`'s casing**, which is `.EXE`. csa-zendesk#80 is the same defect,
found independently in the same week.

## F3 — `auth_status` said ready while every call failed (#510, #495)

A token issued by an OAuth client whose Google Cloud project has been **deleted** stops
refreshing. `auth_status` makes no network call by design, so it saw a well-formed cached token
and reported `ready`; the failure surfaced only as *"could not refresh cached credentials"*, or
as *"Project #… has been deleted"*, with nothing naming the cause.

**Diagnosed by contrast rather than reproduction** — same version, same platform: an install on
`csa-drive-docs-mcp` refreshed and answered `whoami`, while one on the retired
`cino-workspace-mcp` failed every call. `client_project_id`'s own docstring had already named
the mechanism; nothing had connected it to the symptom.

The fix returns `client_retired` **ahead of the token checks**, because `authenticate` against a
retired client fails identically — so a `no_credential` answer would send someone round the loop
that had just failed. **The ordering is the fix**, not the status string.

## F4 — Running another repo's gates reformats this one

`ruff format --check` was run here out of habit from a sibling and reported **"216 files would
be reformatted."** This repo does not use `ruff format`; CI runs `ruff check src tests`, `mypy`,
and two scripts. Acting on that output would have reformatted the codebase on a rule that does
not apply to it.

**Run the gates this repo has, not the ones the last repo had** — which bites hardest during a
cross-repo sweep, when several repos are touched in one sitting.

## F5 — A guard passed a full-suite run while the thing it guards was stale (#483)

The audit-index guard went green while the committed index did not match. Recorded here rather
than only in the issue because the shape recurs across the fleet: a check that derives its
expectation from the same stale artifact it is checking cannot fail.

The fleet-level version is CINO-Platform-Engineering
[`insights/a-green-check-is-only-evidence-about-what-it-ran-on.md`](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/insights/a-green-check-is-only-evidence-about-what-it-ran-on.md).

## F6 — `ls -l` cannot tell a hardened credential from an unhardened one

On Windows, Git Bash renders every file in `~/.csa_google_workspace/` as `-rw-r--r--`, including
the ones `icacls` has narrowed to owner-only. The mode is a rendering; the ACL is the fact.

Use `file_is_owner_only()` — this repo ships it — or `icacls` directly. Anything that reads
`st_mode` is measuring something that does not govern access.

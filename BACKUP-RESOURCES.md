# Backup resources

Exposure, access model and accepted risks are in
[`SECURITY-RESOURCES.md`](SECURITY-RESOURCES.md); CI and the scheduled checks are in
[`OPERATIONAL-RESOURCES.md`](OPERATIONAL-RESOURCES.md). This file answers only the backup
question — and the answer inverts, because everything persistent here is a **credential**.

## What persists, and why none of it should be backed up

| File | What it is | Recoverable? |
|---|---|---|
| `~/.csa_google_workspace/client_secret.json` | CSA's OAuth **client**, distributed by the setup script | Yes — re-run setup. Authority is the Google Cloud project, not this file |
| `~/.csa_google_workspace/token.json` | This operator's access/refresh token | Yes — `authenticate` |
| `~/.csa_google_workspace/token.readonly.json` | The same for the read-only posture, which uses its own cache by design | Yes |

Everything else is source, and git is its recovery story.

**So the correct retention for all three is zero copies.** Losing any of them costs one command.
Copying one puts a credential somewhere nothing is watching. A backup system that has already
swept this directory is a disclosure to assess, not a safety net.

## The finding: a stale backup of a credential is still a credential, and it is not hardened

Measured on the authoring machine, 2026-10-02, using **this repo's own checker**:

```
client_secret.json                            owner_only=True
client_secret.json.20260929-pre-bom-fix.bak   owner_only=False     <-- holds a live client secret
token.json                                    owner_only=True
```

`icacls` on that `.bak`:

```
WINTOP\CodexSandboxUsers:(I)(RX)
NT AUTHORITY\SYSTEM:(I)(F)
BUILTIN\Administrators:(I)(F)
WINTOP\kurt:(I)(F)
```

`(I)` means **inherited**. The current files were narrowed by `_harden`'s
`icacls /inheritance:r /grant:r <user>:F` — the fix for #452, landed in #451 — so they are
owner-only and `file_is_owner_only()` confirms it. **The `.bak` predates that fix**, so it still
carries the directory's inherited ACL, which on this machine grants read-and-execute to a
sandbox-users group.

Three things follow, and the third is the reason this file exists:

1. **The hardening works.** The two current files pass; the one written before it does not. That
   is the clearest evidence available that `_harden` is doing something real.
2. **`ls -l` is useless here.** All of these render `-rw-r--r--` in Git Bash, which is not the
   permission that governs access on Windows and would have made the hardened and unhardened
   files look identical. The ACL is the fact; the mode is a rendering. See
   [`POSIX-AND-WINDOWS.md`](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/POSIX-AND-WINDOWS.md).
3. **Nothing points the detector at stale files.** `file_is_owner_only()` found this in one line,
   and it is only ever called on the path currently in use. A credential-bearing file that is no
   longer referenced is exactly the one nobody re-checks.

**Housekeeping, for anyone reading this on their own machine.** These are safe to delete and
should be — the current scripts no longer create them:

```
~/.csa_google_workspace/client_secret.json.20260929-pre-bom-fix.bak
~/.csa_google_gmail_calendar/client_secret.json.20260929-pre-bom-fix.bak
```

Rotation, if ever needed, is by resetting the secret in the Google Cloud Console — **never by
committing or copying a new file beside the old one.** DesktopSetup#143 was the same pattern one
step upstream: a helper that kept one timestamped backup of a credential-bearing config per run,
forever. It is now bounded to three generations and the copies say what they hold.

## A token can be present, valid-looking, and dead

Worth recording here because it is a *recovery* question that looks like an auth question.

A token issued by an OAuth client whose Google Cloud project has been deleted **cannot be
refreshed and cannot be repaired by logging in again** — `authenticate` against a retired client
fails identically. `auth_status` now reports `client_retired` ahead of the token checks for
exactly that reason (#510, #495): answering `no_credential` would send someone round the loop
that had just failed.

So "restore the token" is never the remedy. **Replace the client, then authenticate.**
`RETIRED_CLIENT_PROJECTS` is hardcoded on purpose — detecting retirement over the network is
precisely the call `auth_status` exists to avoid.

## Elsewhere

- Exposure surface, access model, data classification, accepted risks:
  [`SECURITY-RESOURCES.md`](SECURITY-RESOURCES.md) and [`THREAT_MODEL.md`](THREAT_MODEL.md).
- Scheduled checks and CI: [`OPERATIONAL-RESOURCES.md`](OPERATIONAL-RESOURCES.md).
- How the client reaches a machine in the first place: CSA-Plugins
  [`BACKUP-RESOURCES.md`](https://github.com/CloudSecurityAlliance-Internal/CSA-Plugins/blob/main/BACKUP-RESOURCES.md).

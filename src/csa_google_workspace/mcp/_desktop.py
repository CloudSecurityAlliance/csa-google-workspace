"""Write a working Claude Desktop config, because the user should not have to. (D2)

**The failure is a `PATH` fact, not a bug, and it looks like a bug.** Claude Desktop is a GUI
app, so on macOS it inherits launchd's `PATH` — `/usr/bin:/bin:/usr/sbin:/sbin`. That contains
neither `~/.local/bin`, where `pipx` puts the console script, nor Homebrew; and the `python3` it
*does* contain is macOS's system 3.9, below this package's 3.10 floor. So a bare command name is
not found and `python3` is the wrong interpreter. Claude Code, running in your shell, works
perfectly — which is exactly why this reads as "Desktop is broken" rather than "GUI apps have a
different environment".

The README has documented the fix for months: put the absolute path in the config. That is a
workaround with a hand-edit in it — the user has to know their own home directory, produce valid
JSON, and not clobber the other servers already in that file. **Half the intended clients are
Desktop.** So the tool writes it: it knows its own absolute path, which is the one piece of
information the user was being asked to supply.

The second half, hit immediately after the first: **Desktop has no shell**, so the policy
variables that work in a terminal are simply absent there. The `env` block is the only place
Desktop reads them, so `configure` carries the `CSA_GW_*` variables across — and *only* those,
because it is reading an ambient environment that also holds cloud keys and tokens, into a file
somebody may well screenshot when asking for help.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..auth import _harden

SERVER_KEY = "csa-google-workspace"
SCRIPT_NAME = "csa-google-workspace-mcp"

# Carried into the config, because Desktop has no shell to read them from. `CSA_GW_CLIENT_SECRETS`
# is deliberately NOT here: `login` needs it and the running server never does, because a cached
# token carries its own client id and secret. Writing a credential path into a shared config file
# spreads it for no benefit.
CARRIED_PREFIX = "CSA_GW_"
# `CSA_GW_DEMO_*` are for ONE RUN of the demo and are not policy, but this config is where policy
# state persists — so carrying them turns a value meant for a single run into ambient state that
# outlives it. `CSA_GW_DEMO_SHARE` is a share recipient, which makes it the one that matters
# (CODX-2026-09-01-02). The server path never reads either.
NOT_CARRIED = frozenset({"CSA_GW_CLIENT_SECRETS", "CSA_GW_DEMO_SHARE", "CSA_GW_DEMO_REPO"})


@dataclass
class Result:
    path: Path
    rendered: str
    created: bool
    backup: Path | None
    changed: bool


def config_path(env: Mapping[str, str] | None = None) -> Path:
    """Where Claude Desktop keeps its config on this platform."""
    env = os.environ if env is None else env
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    if sys.platform.startswith("win"):
        base = env.get("APPDATA") or str(Path.home() / "AppData/Roaming")
        return Path(base) / "Claude/claude_desktop_config.json"
    # Linux Desktop is not a shipped target; returning the XDG-ish location is more useful
    # than raising, because `--print` still shows somebody the right JSON to paste.
    return Path.home() / ".config/Claude/claude_desktop_config.json"


def launch_command() -> tuple[list[str], str]:
    """(argv, how it was resolved) — always absolute, never a bare name.

    Three sources, in order of how self-contained the result is:

    1. The console script **beside the running interpreter**. In a `pipx` or venv install this
       is the whole answer: the script's shebang pins the correct Python, so the config needs
       no interpreter and no `PATH`.
    2. The console script anywhere on the *current* `PATH`, resolved to absolute. Correct, and
       one step less certain, because it may not be the install this process came from.
    3. `sys.executable -m csa_google_workspace.mcp`. Always available and always right about
       the interpreter — `sys.executable` is absolute by construction — which is what makes it
       a real fallback rather than a guess.
    """
    beside = Path(sys.executable).parent / SCRIPT_NAME
    if beside.exists():
        return [str(beside)], "the console script beside this interpreter"
    found = shutil.which(SCRIPT_NAME)
    if found:
        return [str(Path(found).resolve())], f"{SCRIPT_NAME} on PATH"
    return [sys.executable, "-m", "csa_google_workspace.mcp"], "this interpreter, with -m"


def carried_env(env: Mapping[str, str]) -> dict[str, str]:
    return {k: v for k, v in sorted(env.items())
            if k.startswith(CARRIED_PREFIX) and k not in NOT_CARRIED}


def entry(env: Mapping[str, str]) -> dict:
    command, _ = launch_command()
    out: dict = {"command": command[0]}
    if len(command) > 1:
        out["args"] = command[1:]
    carried = carried_env(env)
    if carried:
        out["env"] = carried
    return out


# How many timestamped backups of the client config to keep. Enough to recover from a run that
# went wrong plus the one before it; not a permanent archive of every policy ever configured.
KEEP_BACKUPS = 3


def configure(path: Path | None = None, *, env: Mapping[str, str] | None = None,
              dry_run: bool = False) -> Result:
    """Merge this server into Claude Desktop's config, preserving everything else.

    Raises `ValueError` on unreadable JSON rather than replacing it: a file that does not parse
    is most likely one somebody is part-way through editing, and the cost of being wrong about
    that is their other servers.
    """
    env = os.environ if env is None else env
    path = config_path(env) if path is None else Path(path)

    existing: dict = {}
    created = not path.exists()
    if not created:
        try:
            existing = json.loads(path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError as e:
            raise ValueError(
                f"{path} is not valid JSON ({e}), so it has not been touched. Fix or move it "
                f"and run this again - replacing it would remove any other MCP servers "
                f"configured there.") from e
        if not isinstance(existing, dict):
            raise ValueError(f"{path} could not be read as a JSON object, so it was left alone")

    servers = dict(existing.get("mcpServers") or {})
    wanted = entry(env)
    changed = servers.get(SERVER_KEY) != wanted
    servers[SERVER_KEY] = wanted
    merged = {**existing, "mcpServers": servers}
    rendered = json.dumps(merged, indent=2) + "\n"

    if dry_run:
        return Result(path=path, rendered=rendered, created=created, backup=None, changed=changed)

    backup = None
    if not created and changed:
        # Timestamped rather than a single `.bak`, so a second run cannot destroy the copy of
        # the file the user actually hand-wrote.
        backup = path.with_suffix(path.suffix + f".bak.{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(path, backup)
        # copy2 preserves the SOURCE's mode, so a config written by an older version at 0644
        # produced a 0644 backup. A backup of a sensitive file is a sensitive file. (#192)
        _restrict(backup)
        _prune_backups(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    # 0600 EXPLICITLY, and on every run rather than only at creation. No secret VALUE lands
    # here - carried_env() excludes CSA_GW_CLIENT_SECRETS, deliberately - but CSA_GW_TOKEN
    # points a local reader straight at the full-Drive token, and the allowlisted URLs are the
    # policy itself. Rewriting an existing file is the only chance to tighten one an older
    # version left at 0644, and skipping that would leave the exposure with exactly the people
    # who have been using this longest. (#192)
    _restrict(path)
    return Result(path=path, rendered=rendered, created=created, backup=backup, changed=changed)


def _restrict(path: Path) -> None:
    """Owner-only. Best-effort: a filesystem without POSIX modes must not fail a configure.

    Delegates to `auth._harden`, which is where the platform knowledge lives (#451). This used to
    be a bare `path.chmod(0o600)`, and "a filesystem without POSIX modes" turned out not to be a
    hypothetical: on Windows `chmod` moves only the read-only bit, so this silently did nothing
    while the docstring and the call site both said `0600`.

    That mattered more here than almost anywhere else. `CSA_GW_CLIENT_SECRETS` is deliberately
    excluded from this file, but `CSA_GW_TOKEN` points a local reader straight at the full-Drive
    token and the allowlisted URLs are the policy itself - so an unprotected config is a map to
    the credential, sitting beside a credential whose own protection had the same hole. (#453)
    """
    try:
        _harden(str(path))
    except OSError:                       # pragma: no cover - platform-dependent
        pass


def _prune_backups(path: Path) -> None:
    """Keep the newest `KEEP_BACKUPS`, delete the rest.

    Capped rather than dropped: backups exist so a second run cannot destroy a hand-written
    file, and that reason survives. What does not survive is keeping every one since
    installation - each stale copy preserves **a policy the operator believes they have since
    tightened**, sitting beside the current one with an older timestamp. That is worse than
    clutter; it is a contradicting record.

    Sorted by name, which is sorted by time: the stamp is `%Y%m%d-%H%M%S`. Deliberately not by
    mtime, which a backup/restore cycle can reorder.
    """
    backups = sorted(path.parent.glob(path.name + ".bak.*"))
    for stale in backups[:-KEEP_BACKUPS] if KEEP_BACKUPS else backups:
        try:
            stale.unlink()
        except OSError:                   # pragma: no cover - racing another run
            pass

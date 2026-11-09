"""Diagnostics go to stderr, and the client persists them. We only choose the level.

**Measured 2026-08-28, and it is why this module is twenty lines rather than a subsystem.** A
stdio MCP server that writes to stderr already has structured, per-session, timestamped logs on
disk — written by the MCP client:

  * **Claude Code** keeps `~/Library/Caches/claude-cli-nodejs/<project>/mcp-logs-<server>/
    <timestamp>.jsonl` — JSONL, one file per connection, with `sessionId`, `cwd`, an ISO
    timestamp, and our stderr captured **verbatim**.
  * **Claude Desktop** keeps `~/Library/Logs/Claude/mcp-server-<name>.log` — different format,
    same capture, plus the whole JSON-RPC exchange.

Two clients, not coordinating, both already doing it. Their version is also **better than one we
would write**: it is the *parent* capturing the *child*, so it survives the case a log is most
wanted for — failing to start, crashing mid-call, hanging. A file this process writes is missing
exactly then.

So `#145` shrank from "build logging" to "emit more, at a level somebody can turn up". No log
directory, no rotation, no retention, no session ids, no file permissions. All of it is the
client's. Full write-up: `CINO-Engineering/research/mcp-servers/
LOGGING-BELONGS-TO-THE-CLIENT.md`.

## Two rules this module exists to hold

**1. Only an application configures logging.** This is called from `cli.main` and nowhere else. A
*library* that attaches handlers hijacks its embedder's logging, and this project is a library
first — `Workspace` in somebody's application must leave their configuration alone. That is why
the handler goes on the `csa_google_workspace` logger rather than the root one, and why
`propagate` is switched off: an embedder who has configured root should not get our records
twice, and should not get them at all unless they ask.

**2. Raising the level raises detail about the OPERATION, never about the CONTENT.** The client's
capture makes this stricter, not looser — our stderr lands in a cache directory we do not control,
under the client's retention, invisible to us. A debug log of document text would be a persistence
step for an injection payload, somewhere nobody is watching. More verbosity means more about which
call, which file id, what was refused, what Google returned. Never more of what the document said.
`tests/test_logging_level.py` holds both rules.
"""
from __future__ import annotations

import logging
import sys
from collections.abc import Mapping

LEVEL_VAR = "CSA_GW_LOG_LEVEL"
DEFAULT_LEVEL = "WARNING"

# Python's five, and only Python's five. MCP's own logging capability uses syslog's eight
# (`debug` `info` `notice` `warning` `error` `critical` `alert` `emergency`) — but that is the
# `ctx.log` channel, whose level the CLIENT sets at runtime via `logging/setLevel`. This variable
# governs our stderr, so it speaks Python. Nothing here is ever `alert` or `emergency`; a
# document-editing server has no paging events.
LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

_ROOT = "csa_google_workspace"


def level_from_env(env: Mapping[str, str]) -> str:
    """`CSA_GW_LOG_LEVEL`, defaulting to WARNING — and refusing to guess.

    An unrecognised value is an error rather than a silent fallback. The failure mode of guessing
    is somebody who set `LOG_LEVEL=verbose` to diagnose a problem, saw no extra output, and
    concluded the tool has nothing more to say.
    """
    raw = (env.get(LEVEL_VAR) or "").strip().upper()
    if not raw:
        return DEFAULT_LEVEL
    if raw not in LEVELS:
        raise ValueError(
            f"{LEVEL_VAR}={raw!r} is not a log level. Use one of: {', '.join(LEVELS)}. "
            f"Default is {DEFAULT_LEVEL} — quiet unless something is wrong.")
    return raw


def configure(env: Mapping[str, str]) -> str:
    """Attach one stderr handler to this package's logger. Returns the level applied.

    **stderr, explicitly.** Not `basicConfig`, which touches the root logger, and never stdout —
    under stdio that IS the JSON-RPC channel, and one stray line corrupts the session in a way
    that looks like a hung server from the client end.

    Idempotent: called twice, it replaces rather than doubling. `login` and the server share an
    entry point, and a duplicated handler prints everything twice, which reads like a loop.
    """
    level = level_from_env(env)
    logger = logging.getLogger(_ROOT)

    for existing in [h for h in logger.handlers if getattr(h, "_csa_gw", False)]:
        logger.removeHandler(existing)

    handler = logging.StreamHandler(sys.stderr)
    handler._csa_gw = True                       # type: ignore[attr-defined]
    # No timestamp: the client stamps every line as it captures it, and ours would be a second,
    # slightly different one in the same record. Level and logger name are what it cannot add.
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(level)
    # An embedder who configured the root logger should not receive our records as well; and
    # nothing here should reach a handler this process did not install.
    logger.propagate = False
    return level

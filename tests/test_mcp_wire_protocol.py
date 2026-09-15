"""The JSON-RPC a standards-compliant MCP client actually receives, driven over real stdio.

**RR-006**, from the 2026-09-01 correctness review. Everything else in this suite exercises the
server *in process*, through the SDK's Python objects. That leaves the wire unasserted — and the
wire is what clients parse for protocol negotiation, display, logging and compatibility decisions.

The gap was not theoretical. `serverInfo.version` shipped **empty** from the day the server
existed until v0.36.1, because `MCPServer` defaults `version` to `""`; the test written for that
fix asserts it on the Python object, so it would still pass if the value never reached the wire.
An external reviewer found the original bug with a stdio probe, which is the argument for these
tests existing at all.

**Four attempts were needed to write the first probe**, and the reason belongs here because it is
the knowledge these tests encode:

* `server/discover` before `initialize` -> `Method not found`.
* `initialize` with `params.protocolVersion: "2026-07-28"` negotiates **down** to `2025-11-25` —
  that field is the *legacy* handshake, so asking for the modern version through it gets you the
  old one, and `server/discover` is then gated off as unreachable for a legacy peer.
* The modern handshake carries the version in `params._meta` under
  `io.modelcontextprotocol/protocolVersion`, and the envelope **also requires**
  `io.modelcontextprotocol/clientCapabilities` — omitting it is `-32602`, not a default.

Costly to rediscover, and invisible from the Python API.
"""
from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import time

import pytest

from csa_google_workspace import __version__

PROTOCOL_VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
CLIENT_CAPABILITIES_KEY = "io.modelcontextprotocol/clientCapabilities"
SERVER_INFO_KEY = "io.modelcontextprotocol/serverInfo"
MODERN = "2026-07-28"
LEGACY = "2025-11-25"


def speak(*requests: dict, env_extra: dict | None = None, timeout: int = 60):
    """Run the server as a subprocess, send JSON-RPC on stdin, parse stdout as a client would.

    **Reads until every request id has an answer, rather than writing and closing stdin.** The
    first version used `communicate()`, which closes stdin immediately — and the server can then
    reach EOF and shut down before draining a queued request. That passed on four Python versions
    and failed on 3.12 with `IndexError`, which is the shape of a race rather than a defect: a
    flaky test is worse than no test, because it teaches people to re-run CI.

    A deliberately minimal environment: no token is configured, because the server starts without
    one by design and every assertion here is about the protocol rather than about Drive.

    MINIMAL AND VIABLE ARE DIFFERENT PROPERTIES, and on Windows this harness had only the first
    (#453). Without `SystemRoot`, Winsock cannot initialise, so `asyncio` fails on IMPORT:

        File "...\\asyncio\\windows_events.py", line 8, in <module>
            import _overlapped
        OSError: [WinError 10106] The requested service provider could not be loaded or initialized

    The server therefore died before reading stdin, and the loop below reported "no answer within
    60s" **while failing in half a second** - a diagnosis that is the opposite of what happened.
    All 13 tests in this file failed that way, on every Windows machine, invisibly, because CI is
    ubuntu-only.

    `SystemRoot` is added and nothing else. It is platform plumbing rather than configuration, and
    measured sufficient. In particular `USERPROFILE`, `APPDATA` and `LOCALAPPDATA` are deliberately
    still absent: they are what `~` resolves through, and exposing them would let the server find a
    developer's real `~/.csa_google_workspace/client_secret.json` - which is exactly the
    hermeticity the `CSA_GW_TOKEN` line below exists to protect.
    """
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": os.pathsep.join(sys.path[:1] + [str(_src())]),
        "CSA_GW_ALLOWLIST_READ": "*",
        # Somewhere that cannot exist, so a developer's real cached token is never touched.
        "CSA_GW_TOKEN": "/nonexistent/csa-gw-wire-test/token.json",
    }
    if os.name == "nt":
        env["SystemRoot"] = os.environ["SystemRoot"]
    env.update(env_extra or {})
    proc = subprocess.Popen(
        [sys.executable, "-m", "csa_google_workspace.mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=env, bufsize=1)
    expected = {r["id"] for r in requests if "id" in r}
    messages: list[dict] = []
    lines: list[str] = []
    deadline = time.monotonic() + timeout
    try:
        for request in requests:
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
        seen: set = set()
        while seen != expected and time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:                            # the server closed stdout
                break
            if not line.strip():
                continue
            lines.append(line)
            message = json.loads(line)
            messages.append(message)
            if "id" in message:
                seen.add(message["id"])
        if seen != expected:
            pytest.fail(f"no answer for request id(s) {sorted(expected - seen)} within "
                        f"{timeout}s; got {len(messages)} message(s)")
    finally:
        # stdin is closed only AFTER the answers are in, so EOF cannot race the last request.
        with contextlib.suppress(Exception):
            proc.stdin.close()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=15)
        if proc.poll() is None:                     # pragma: no cover - CI hang guard
            proc.kill()
        err = proc.stderr.read()
    return messages, "".join(lines), err


def _src():
    from pathlib import Path
    return Path(__file__).resolve().parent.parent / "src"


def discover(version: str = MODERN) -> dict:
    return {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
            "params": {"_meta": {PROTOCOL_VERSION_KEY: version,
                                 CLIENT_CAPABILITIES_KEY: {}}}}


def initialize(version: str = LEGACY, request_id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "method": "initialize",
            "params": {"protocolVersion": version, "capabilities": {},
                       "clientInfo": {"name": "wire-test", "version": "0"}}}


class TestTheModernDiscoveryHandshake:
    def test_discover_answers_complete(self):
        messages, _out, _err = speak(discover())
        result = messages[0]["result"]
        assert result["resultType"] == "complete"

    def test_it_advertises_the_modern_protocol_version(self):
        messages, _out, _err = speak(discover())
        assert messages[0]["result"]["supportedVersions"] == [MODERN]

    def test_the_server_version_reaches_the_wire(self):
        """The assertion that would have caught the original defect. The in-process test for the
        same fix reads a Python attribute; this reads what a client is sent."""
        messages, _out, _err = speak(discover())
        info = messages[0]["result"]["_meta"][SERVER_INFO_KEY]
        assert info["version"] == __version__
        assert info["version"], "serverInfo.version was empty on the wire for 34 releases"
        assert info["name"] == "csa-google-workspace"

    def test_the_cache_envelope_is_present(self):
        """`ttlMs` and `cacheScope` tell a client whether it may reuse this. Absent, a client
        caches on its own guess."""
        result = speak(discover())[0][0]["result"]
        assert result["ttlMs"] == 0
        assert result["cacheScope"] == "private"

    def test_the_envelope_requires_client_capabilities(self):
        """Not a default. Omitting it is an invalid-params error, which is worth pinning because
        three probes were written wrong before this was understood."""
        bad = {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
               "params": {"_meta": {PROTOCOL_VERSION_KEY: MODERN}}}
        messages, _out, _err = speak(bad)
        assert messages[0]["error"]["code"] == -32602
        assert CLIENT_CAPABILITIES_KEY in messages[0]["error"]["message"]


class TestTheLegacyHandshakeStillWorks:
    def test_initialize_negotiates_the_legacy_version(self):
        messages, _out, _err = speak(initialize(LEGACY))
        assert messages[0]["result"]["protocolVersion"] == LEGACY

    def test_the_server_version_reaches_the_wire_there_too(self):
        result = speak(initialize(LEGACY))[0][0]["result"]
        assert result["serverInfo"]["version"] == __version__

    def test_asking_for_the_modern_version_through_the_legacy_field_gets_legacy(self):
        """Records a real trap rather than an aspiration: `params.protocolVersion` IS the legacy
        channel, so a client using it cannot reach the modern protocol however new the value it
        sends. `server/discover` is then unreachable, which is correct and surprising."""
        messages, _out, _err = speak(initialize(MODERN))
        assert messages[0]["result"]["protocolVersion"] == LEGACY


class TestStdoutIsOnlyTheProtocol:
    """Under stdio, **stdout IS the JSON-RPC channel**. One stray `print` corrupts it, and this
    project has already had that bug. Asserted at the only layer where it is visible."""

    def test_every_stdout_line_is_json(self):
        _messages, out, _err = speak(initialize(), discover())
        for line in out.splitlines():
            if line.strip():
                json.loads(line)          # raises if anything non-protocol was written

    def test_logging_goes_to_stderr_not_stdout(self):
        _messages, out, err = speak(initialize(), env_extra={"CSA_GW_LOG_LEVEL": "DEBUG"})
        assert err.strip(), "DEBUG logging produced nothing on stderr"
        for line in out.splitlines():
            if line.strip():
                json.loads(line)

    def test_a_startup_warning_does_not_reach_stdout(self):
        """`CSA_GW_ALLOWLIST_READ=*` warns at startup. That warning must not land on stdout."""
        _messages, out, err = speak(initialize())
        assert "EVERY file" in err or "every file" in err.lower()
        for line in out.splitlines():
            if line.strip():
                json.loads(line)


class TestToolsOverTheWire:
    def test_tools_list_returns_the_surface(self):
        messages, _out, _err = speak(
            initialize(),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        listed = [m for m in messages if m.get("id") == 2]
        assert listed, "tools/list produced no response"
        tools = listed[0]["result"]["tools"]
        assert len(tools) > 40, f"only {len(tools)} tools on the wire"
        names = {t["name"] for t in tools}
        assert {"list_comments", "read_file_content", "describe_configuration"} <= names

    def test_each_tool_carries_an_input_schema_on_the_wire(self):
        """`inputSchema` on the wire, whatever the Python attribute is called - the SDK renamed
        it to `input_schema` in 2.x, and a client reads the JSON name."""
        messages, _out, _err = speak(
            initialize(),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        listed = [m for m in messages if m.get("id") == 2]
        # Guarded rather than indexed. The first version did `[...][0]` and, when the response
        # raced EOF, failed with `IndexError: list index out of range` - which says nothing about
        # what went wrong. `speak` no longer allows that race, and this still reads clearly if
        # something else ever eats the response.
        assert listed, "tools/list produced no response"
        tools = listed[0]["result"]["tools"]
        missing = [t["name"] for t in tools if "inputSchema" not in t]
        assert missing == [], f"tools with no inputSchema on the wire: {missing}"

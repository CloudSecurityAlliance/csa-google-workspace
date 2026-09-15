"""The README's tool list must equal what the server registers.

It had drifted, and in the direction that costs most: the list named fifteen tools while the
server registered twenty-five, so every content-write tool, `create_file`, `copy_file`,
`list_slides`, `edit_comment` and `delete_comment` were invisible to anyone deciding whether
this project does what they need. A README that undersells is not a cosmetic problem - it is
the only thing most readers will ever look at.

Prose is checked by nobody, so it is checked here instead.
"""
from __future__ import annotations

import asyncio
import pathlib
import re

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server

README = pathlib.Path(__file__).resolve().parent.parent / "README.md"


def registered_tools() -> set[str]:
    """Every tool a fully configured server exposes.

    Settings are supplied because three tools (`authenticate`, `describe_configuration`,
    `report_a_problem`) register only with them, and it is the configured server the README
    describes.
    """
    settings = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*"})
    server = create_server(lambda: Workspace(FakeBackend()), settings=settings)
    return {tool.name for tool in asyncio.run(server.list_tools())}


def documented_tools() -> set[str]:
    """Tool names from the README's own tool table.

    Bounded to that table rather than the whole file: the comparison tables further down name
    tools alongside `—` rows for capabilities that have no tool, and prose elsewhere mentions
    tools in passing. Only the table that claims to be the list is the list.
    """
    text = README.read_text(encoding="utf-8")
    start = text.index("**Tools** —")
    end = text.index("The find-and-read names", start)
    return set(re.findall(r"`([a-z_]+)`", text[start:end]))


def test_the_readme_lists_every_tool_the_server_registers():
    missing = registered_tools() - documented_tools()
    assert missing == set(), (
        f"registered but not in the README's tool table: {sorted(missing)}. A reader deciding "
        f"whether this project does what they need will never find them.")


def test_the_readme_does_not_promise_tools_that_do_not_exist():
    invented = documented_tools() - registered_tools()
    assert invented == set(), (
        f"the README's tool table names tools the server does not register: {sorted(invented)}")


def test_the_stated_count_matches():
    """The count is the first thing a skimmer reads, so it has to be true."""
    stated = re.search(r"\*\*Tools\*\* — (\d+),", README.read_text(encoding="utf-8"))
    assert stated, "the tool table no longer states a count"
    assert int(stated.group(1)) == len(registered_tools())


# ── The comparison table ─────────────────────────────────────────────────────────────
#
# The tests above are bounded to the manifest table on purpose — "only the table that claims
# to be the list is the list" — and that left the comparison table 200 lines further down
# completely unguarded. It drifted, badly: five tools that shipped in 0.15.0 were still marked
# `✗ planned` ten releases later, and the count still said 13 when the server registered 31.
# Somebody reading to decide whether this project does what they need was being told it does
# less than it does, by the project itself.
#
# A different rule is needed here, because this table legitimately contains rows that are NOT
# tools (`—` for capabilities with no tool, prose in the first cell). So instead of "the table
# equals the registry", the rule is two-directional and narrower:
#
#   a registered tool may never be marked planned    (undersell — what actually happened)
#   an unregistered tool may never be marked shipped (oversell — the worse failure)

COMPARISON_START = "### Tool-by-tool comparison"
COMPARISON_END = "### The same table, by underlying API"

# Their tool sets, read from live schemas rather than documentation (research/
# drive-mcp-servers-and-api-surface.md). Written out so the parity CLAIMS in the table are
# checked against something, rather than against themselves: renaming one of ours to a
# non-shared name would silently break transferability, and this is what would notice.
GOOGLE_TOOLS = frozenset({
    "search_files", "list_recent_files", "get_file_metadata", "get_file_permissions",
    "read_file_content", "download_file_content", "create_file", "copy_file"})
CLAUDE_TOOLS = GOOGLE_TOOLS | {"update_file", "share_file", "trash_file"}


def comparison_rows() -> list[tuple[set[str], str]]:
    """(tool names in the row, what the `Ours` column says) for each row of the table."""
    text = README.read_text(encoding="utf-8")
    body = text[text.index(COMPARISON_START):text.index(COMPARISON_END)]
    rows = []
    for line in body.splitlines():
        if not line.startswith("|") or set(line) <= set("|- "):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 5 or cells[0] == "Tool":          # header
            continue
        rows.append((set(re.findall(r"`([a-z_]+)`", cells[0])), cells[4]))
    return rows


def test_the_comparison_table_does_not_call_a_shipped_tool_planned():
    """The drift that actually happened, and the direction that costs a reader most."""
    registered = registered_tools()
    undersold = {name for names, ours in comparison_rows() for name in names
                 if name in registered and ("planned" in ours or ours.startswith("✗"))}
    assert undersold == set(), (
        f"the comparison table says these are not built, and the server registers them: "
        f"{sorted(undersold)}")


def test_the_comparison_table_does_not_claim_a_tool_that_does_not_exist():
    registered = registered_tools()
    oversold = {name for names, ours in comparison_rows() for name in names
                if name not in registered and ours.startswith("✅")}
    assert oversold == set(), (
        f"the comparison table marks these as shipped and the server does not register them: "
        f"{sorted(oversold)}")


def test_the_stated_tool_counts_are_arithmetic_that_holds():
    """Three numbers in the `Where this actually stands` table, all checkable."""
    text = README.read_text(encoding="utf-8")
    registered = registered_tools()

    row = re.search(r"\| MCP tools \| (\d+) \| (\d+) \| \*\*(\d+)\*\* \|", text)
    assert row, "the MCP tools row no longer has the shape this test reads"
    assert int(row.group(1)) == len(GOOGLE_TOOLS)
    assert int(row.group(2)) == len(CLAUDE_TOOLS)
    assert int(row.group(3)) == len(registered), (
        f"the table says we have {row.group(3)} tools; the server registers {len(registered)}")

    have = re.search(r"\*\*Of their tools, we have\*\* \| \*\*(\d+) of (\d+)\*\* \| "
                     r"\*\*(\d+) of (\d+)\*\*", text)
    assert have, "the parity row no longer has the shape this test reads"
    assert (int(have.group(1)), int(have.group(2))) == (
        len(GOOGLE_TOOLS & registered), len(GOOGLE_TOOLS))
    assert (int(have.group(3)), int(have.group(4))) == (
        len(CLAUDE_TOOLS & registered), len(CLAUDE_TOOLS))

    extra = re.search(r"\| Tools they do not have \| — \| — \| \*\*(\d+)\*\* \|", text)
    assert extra, "the surplus row no longer has the shape this test reads"
    assert int(extra.group(1)) == len(registered - CLAUDE_TOOLS)

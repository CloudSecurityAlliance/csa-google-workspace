"""Restrict this server to another Drive server's surface — allowed *and* advertised.

`CSA_GW_FLAVOUR=google|claude|full`, default `full`.

**A flavour is a surface guarantee, and it has two halves that only work together.** Only those
tools are allowed, and **only those tools are advertised** — the rest are never registered.

The second half is the point, and it is what an earlier framing of this feature missed. Matching
names is not a drop-in replacement: a model shown 56 tools behaves differently from one shown 11,
however identical the eleven are. It plans differently, reaches for things that are not there in
the server it is standing in for, and spends context on schemas it will never call. Advertising
without allowing would be a lie; allowing without advertising is what this server did until now.

## What the vendors actually expose

Verified against live schemas (`research/drive-mcp-servers-and-api-surface.md`), not from docs.
The claude.ai connector publishes **11**; Google's publishes those minus the three it declines to
ship — `update_file`, `share_file`, `trash_file` — for **8**.

The shared tools are genuinely the same tools: names and parameters match, and only the
descriptions differ. That alignment work landed long before this switch and is what makes the
switch cheap.

## Why some tools survive every flavour

`ALWAYS` is not a hedge. A flavour restricts **the Drive surface** — which operations on
documents exist. It is not a promise to be unusable or undiagnosable:

* **`authenticate`** — without it, an install with no cached token has no way to get one, and the
  server is bricked rather than restricted. Google's server has no equivalent because it is
  hosted and authorized elsewhere; ours is a local subprocess and this is how it is switched on.
* **`describe_configuration`** — this is *where the server says what it is hiding*. Hiding the
  tool that explains the hiding would be perverse.
* **`read_server_resource`** — the route to `csa-gw://help/capabilities`, which is what a model
  reads to learn a thing is impossible rather than guessing. Several clients surface resources
  only to the user, so without this tool the model cannot reach them at all.

Everything else is Drive surface and is filtered.

## The tradeoff this must handle

Hiding a tool changes what a refusal looks like. With `share_file` registered but gated, an agent
gets *"the `file.share` capability is disabled for this server; an operator enables it in
configuration"* — informative, and relayable to the user. An **absent** tool instead reads as
*"this server cannot do that"*, and the model may report it as impossible or go looking for
another route — the route-around-a-refusal failure `csa-gw://help/capabilities` exists to prevent.

So a flavour **says what it is hiding**: in the server instructions the model reads at startup,
and in `describe_configuration`. Restriction that announces itself is a restriction; restriction
that is silent is a missing feature.
"""
from __future__ import annotations

from collections.abc import Mapping

FLAVOUR_VAR = "CSA_GW_FLAVOUR"
DEFAULT_FLAVOUR = "full"

# The claude.ai Drive connector's surface: 6 read + 5 write.
_CLAUDE = frozenset({
    "search_files", "list_recent_files", "get_file_metadata", "get_file_permissions",
    "read_file_content", "download_file_content",
    "create_file", "update_file", "copy_file", "share_file", "trash_file",
})

# Google's own Drive MCP server: the same, minus the three it declines to ship. That is a
# deliberate choice by a vendor who could have exposed more, which is exactly why it is worth
# being able to adopt wholesale.
_GOOGLE = _CLAUDE - {"update_file", "share_file", "trash_file"}

# Present under every flavour — see the module docstring. These are not Drive operations.
# `auth_status` and `whoami` join them: no deployment should be able to narrow itself out of
# being able to say whether it is logged in and as whom. Neither appears in Google's or Claude's
# published surface, so a flavour would otherwise drop both - and an operator who has narrowed a
# deployment still needs to answer "which account is this acting as" before trusting a write.
ALWAYS = frozenset({"authenticate", "auth_status", "whoami",
                    "describe_configuration", "read_server_resource"})

# `None` means "no restriction", which is different from "an empty set".
FLAVOURS: dict[str, frozenset[str] | None] = {
    "full": None,
    "google": _GOOGLE,
    "claude": _CLAUDE,
}

_LABEL = {
    "google": "Google's own Drive MCP server",
    "claude": "the claude.ai Drive connector",
    "full": "this server's own surface",
}


def flavour_from_env(env: Mapping[str, str]) -> str:
    """`CSA_GW_FLAVOUR`, defaulting to `full`, refusing to guess.

    An unrecognised value is an error rather than a silent fallback to `full`. Falling back would
    be the worst outcome available: somebody who typed `CSA_GW_FLAVOUR=googl` to *restrict* the
    server would get the unrestricted one, and nothing would say so.
    """
    raw = (env.get(FLAVOUR_VAR) or "").strip().lower()
    if not raw:
        return DEFAULT_FLAVOUR
    if raw not in FLAVOURS:
        raise ValueError(
            f"{FLAVOUR_VAR}={raw!r} is not a known flavour. Use one of: "
            f"{', '.join(FLAVOURS)}. `google` and `claude` restrict this server to that "
            f"vendor's tool surface — those tools and no others, advertised and allowed. "
            f"`full` is this server's own surface and is the default.")
    return raw


def permitted(flavour: str) -> frozenset[str] | None:
    """The tool names a flavour publishes, or `None` for no restriction."""
    tools = FLAVOURS[flavour]
    return None if tools is None else tools | ALWAYS


def instruction_note(flavour: str) -> str:
    """What the model is told at startup. No counts — see `describe` for why.

    `MCPServer.instructions` is read-only and set at construction, before any tool is
    registered, so a hidden-count is not available here. That is no loss: the count is a
    diagnostic, and what the model needs at startup is the *rule* — absent means switched off,
    not impossible.
    """
    if flavour == DEFAULT_FLAVOUR:
        return ""
    return (
        f"\n\nTOOL SURFACE RESTRICTED. This server is running the `{flavour}` flavour, so it "
        f"publishes only the tools {_LABEL[flavour]} publishes. Tools you might expect from this "
        f"server are deliberately not registered.\n\n"
        f"A tool that is absent here is SWITCHED OFF BY CONFIGURATION, not impossible. If the "
        f"user asks for something you have no tool for, say that this server is running a "
        f"restricted surface and an operator can change it — do not report it as unsupported, "
        f"and do not reach for another integration to do it instead. `describe_configuration` "
        f"names the flavour and counts what is hidden."
    )


def describe(flavour: str, published: int, hidden: int) -> str:
    """The counted form, for `describe_configuration` and `csa-gw://config`.

    The count is what makes it actionable. "Restricted to Google's surface" tells somebody
    nothing they can act on; "11 published, 45 hidden" tells them the tool they wanted almost
    certainly exists and is switched off — the difference between reporting a limitation and
    reporting a configuration.
    """
    if flavour == DEFAULT_FLAVOUR:
        return ""
    return (f"Flavour `{flavour}`: publishing only what {_LABEL[flavour]} publishes — "
            f"{published} tools registered, {hidden} of this server's own tools hidden. "
            f"Anything absent is switched off here, not impossible.")

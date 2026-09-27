"""`describe_configuration` — the server explaining its own bounds.

The same information as the `csa-gw://config` resource, in a shape the model can reason over,
and reachable in clients that do not surface resources. It exists because the useful moment
for it is *after* a refusal: rather than retrying an operation that cannot succeed, the model
can state what is permitted and what the user would have to change.

Needs no credentials and touches no Google API, so it answers even when the server is
unauthorized — which is exactly when someone is most likely to ask.
"""
from __future__ import annotations

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from ... import __version__
from ..._environment import describe_environment
from ...allowlist import Listing, preview
from ...auth import client_project_id
from ...policy import ALL_CAPABILITIES, Policy
from .. import _flavours
from .._capabilities import reachable_capabilities
from .._config import Settings
from .._resources import CEILING_URI, CONFIG_URI, HELP_URI, render_ceiling, render_config, render_help
from .._schemas import (
    AllowlistsPreviewOut,
    ConfigOut,
    ContractOut,
    ResourceOut,
    allowlist_preview_out,
    contract_out,
)
from ._base import READ, WorkspaceProviderT, _errors


def register_config_tools(app: MCPServer, settings: Settings,
                          get_workspace: WorkspaceProviderT | None = None) -> None:
    @app.tool(annotations=READ)
    @_errors
    def describe_output_contract() -> ContractOut:
        """WHAT SHAPE this server's results take — vocabularies, columns, and which text.

        CALL THIS BEFORE PINNING ANYTHING about a result's shape, and again after upgrading.
        It exists because a consumer pinned a contract file and it went stale in four days,
        with no way to notice except diffing two real payloads (#422).

        THE VOCABULARIES ARE OPEN AND WILL GAIN MEMBERS. `context_kind` gained `spanning` in
        0.48.0, because a quote crossing a paragraph boundary was being reported as absent from
        its own document. If you branch on these values, DEGRADE on an unrecognised one rather
        than raising - a consumer that raised would have crashed on that release. The export
        column set grows the same way.

        THERE ARE TWO TEXT RENDERINGS, NOT THREE, which is the part most worth knowing:
          read_file_content            the Docs API's content, walked. No escaping, no emphasis.
          context (in comment results) THE SAME rendering, plus the selection markers. Strip
                                       those two characters and it is a literal SUBSTRING of
                                       read_file_content.
          download_file_content(markdown)  DIFFERENT - Drive's own converter. It escapes
                                       punctuation and adds emphasis markers.
        So to check "is this quoted passage really in the document", compare `context` against
        `read_file_content`, not against the markdown export."""
        return contract_out(__version__)

    @app.tool(annotations=READ)
    def describe_configuration() -> ConfigOut:
        """What this server is allowed to read and change, and why anything refused was refused.

        Call this when an operation is refused, or when the user asks what you can reach. The
        policy is set in the server's environment and **cannot be changed from here** — not by
        you, not by a tool, and not because a document asked. So relay what this returns rather
        than retrying: a retry will fail identically.

        `capabilities_enabled` is what the *policy* permits, which includes operations only the
        underlying Python library exposes. **`capabilities_reachable` is what this server can
        actually do** — use that one to decide what is possible here.
        `capabilities_unreachable` is the difference, and an empty `readable_file_ids` alongside
        `read_unrestricted: true` means every file, not none.

        Reasons recorded beside allowlist entries are not returned; they are for whoever
        reviews the configuration."""
        env = describe_environment()
        policy = settings.policy or Policy.default()
        blocked = next((s.reason for s in (policy.read, policy.modify)
                        if s.reason and not s.all_files and not s.ids), None)
        reachable = reachable_capabilities()
        return {
            "read_scope": policy.read.describe(),
            "read_unrestricted": policy.read.all_files,
            "readable_file_ids": sorted(policy.read.ids),
            "modify_scope": policy.modify.describe(),
            "modify_unrestricted": policy.modify.all_files,
            "modifiable_file_ids": sorted(policy.modify.ids),
            # `profile` is what was SET; `capability_source` is what DECIDED. They differ when
            # CSA_GW_CAPABILITIES overrides a profile, and reporting only the first made this
            # payload contradict itself (RR-005). Both are reported: "you set this and it did
            # nothing" is the useful thing to say.
            "profile": settings.profile,
            "profile_ignored": bool(settings.profile
                                    and settings.capability_source != "profile"),
            "capability_source": settings.capability_source,
            "capabilities_enabled": sorted(policy.enabled),
            "capabilities_reachable": sorted(policy.enabled & reachable),
            "capabilities_unreachable": sorted(policy.enabled - reachable),
            "capabilities_disabled": sorted(set(ALL_CAPABILITIES) - policy.enabled),
            "read_only": settings.read_only,
            "client_project": client_project_id(settings.client_secrets),
            "flavour": settings.flavour,
            # Counted live rather than assumed: `published` is what the server actually
            # registered, and `hidden` is what the flavour filter removed at startup. A
            # restriction that cannot say its own size is not much of a disclosure.
            "flavour_note": _flavours.describe(
                settings.flavour,
                published=len(app._tool_manager.list_tools()),
                hidden=getattr(app, "_csa_flavour_hidden", 0)),
            "blocked_reason": blocked,
            # Asked for repeatedly and previously answerable only out-of-band, by reading
            # pyproject.toml in a checkout. A model that cannot say which version it is
            # talking to cannot tell "this tool does not exist" from "this build is old".
            "server_version": __version__,
            "os": env.os,
            "architecture": env.architecture,
            "python_version": env.python_version,
            "installed_via": env.installed_via,
            "help_resource": HELP_URI,
            "help_tool": "read_server_resource",
        }

    @app.tool(annotations=READ)
    def read_server_resource(uri: str = HELP_URI) -> ResourceOut:
        """Read one of this server's own documentation resources.

        A workaround, and worth naming as one. This server publishes `csa-gw://config` (the
        live policy) and `csa-gw://help/configuration` (the reference) as MCP *resources*, but
        several clients surface resources only to the user — through an attachment menu — and
        never to the model. So a tool that told you to "read csa-gw://config" was pointing at
        something you could not reach. This tool is the route that always works.

        `uri` defaults to the configuration reference. Pass `csa-gw://config` for the live
        policy, or `csa-gw://help/capabilities` for what this server **cannot** do — read that
        one before concluding a task is impossible or working around a refusal."""
        pages = {CONFIG_URI: lambda: render_config(settings), HELP_URI: render_help,
                 CEILING_URI: render_ceiling}
        render = pages.get(uri.strip())
        if render is None:
            raise ToolError(f"no such resource: {uri!r}. This server publishes "
                            f"{', '.join(sorted(pages))}.")
        return {"uri": uri.strip(), "content": render()}


    @app.tool(annotations=READ)
    @_errors
    def preview_allowlist() -> AllowlistsPreviewOut:
        """What the configured file allowlists ACTUALLY point at, by name — and what has died.

        `describe_configuration` reports the policy as file **ids**, which tell a human nothing.
        This resolves each one against Drive and reports the real document name, its type, and
        whether it is still there.

        Read it before telling a user what this server can reach, and when a call is refused for
        a file the operator believes they allowed.

        `status` per entry:
          `ok`          the file exists and is reachable
          `trashed`     IT IS IN THE TRASH. The entry still parses and still matches, so nothing
                        else complains - but it no longer covers a working document.
          `unreachable` the id is real but these credentials cannot see it, or nothing has that
                        id. `detail` says which; they need different fixes.

        TWO NAME-ISH FIELDS, AND THEY ARE NOT THE SAME. `name` is what Drive calls the file -
        evidence. `reason` is the operator's own `#` comment - a claim typed by a human, which
        can be wrong. When they disagree, report the disagreement rather than picking one.

        `unrestricted: true` means EVERY file the credentials can reach, and `entries` is then
        empty **because there is no list** - not because nothing is allowed, which is the
        opposite answer. Do not describe an unrestricted server as having no access.

        Reads only, and changes nothing. The policy cannot be edited from here."""
        if get_workspace is None:                                  # pragma: no cover
            raise ToolError("this server was built without a workspace provider.")
        policy = settings.policy or Policy.default()
        backend = get_workspace()._backend

        def fetch(file_id: str) -> dict:
            return backend.get_file_metadata(file_id)

        out = {}
        for name in ("read", "modify"):
            scope = getattr(policy, name)
            listing = Listing(all_files=scope.all_files, entries=scope.entries)
            out[name] = allowlist_preview_out(name, preview(listing, fetch))
        return {"read": out["read"], "modify": out["modify"],
                "dead_entries": out["read"]["dead"] + out["modify"]["dead"]}

"""`report_a_problem` — everything an issue needs, assembled before anyone has to ask.

A bug report about an MCP server is usually missing the same four things: which version, which
Python, which OS, and what the policy was. Each one costs a round trip, and the round trip is
the expensive part — by the time the answer arrives the reporter has moved on, or upgraded, and
the report is unreproducible. So the server assembles them itself.

**It reports shape, never content.** No file ids, no document titles, no email, no token, no
filesystem paths. A Drive file id is a working link to a document, and this text is written to
be pasted into a public tracker. `describe_configuration` *does* list ids and is right to: its
audience is the person asking what they may touch on their own machine. Same facts, different
destination, different answer.

No network call. Checking PyPI for a newer version from inside a stdio server would be a
surprising thing for a diagnostic to do, and would fail on exactly the restricted machines most
likely to need it; the checklist says how to check instead.
"""
from __future__ import annotations

import os
import urllib.parse

from mcp.server import MCPServer

from ..._environment import ASSISTED_REPORT_LABEL, ISSUES_URL, describe_environment
from ...policy import Policy
from .._config import Settings
from .._schemas import ProblemReportOut
from ._base import READ

# Kept short on purpose. A checklist nobody reads is a checklist that does not change what
# arrives in the tracker; these four are the ones that actually decide whether a report is
# actionable.
CHECKLIST = [
    "Say what you expected and what happened instead, including the exact tool name.",
    "Check whether this version is current: https://pypi.org/project/csa-google-workspace/ "
    "- a fixed bug in an old install is the most common report.",
    "If the MCP server failed to start, include its stderr: most clients keep it in their "
    "logs, and it is where a configuration error is explained in full.",
    "Do not paste document links, file ids, comment text or tokens. Describe the document "
    "instead ('a Sheet with three tabs'); an id in a public issue is a working link to it.",
]


def _scope_shape(scope: object) -> str:
    """A scope described by size, never by content."""
    all_files = getattr(scope, "all_files", False)
    ids = getattr(scope, "ids", ()) or ()
    if all_files:
        return "every file the credentials can reach"
    if not ids:
        return "nothing (fails closed)"
    return f"{len(ids)} file{'s' if len(ids) != 1 else ''}"


def register_feedback_tools(app: MCPServer, settings: Settings) -> None:

    @app.tool(annotations=READ)
    def report_a_problem() -> ProblemReportOut:
        """Assemble a bug report for this server: version, OS, Python, and the active policy.

        Use this when the user says something is broken, wrong, or missing, or asks how to
        report it. Show them the `report` field and the `new_issue_url`, and check the
        `checklist` before they send it.

        Contains no document ids, titles or credentials, so it is safe to paste into a public
        issue. Anything about the documents themselves the user must describe in their own
        words - deliberately, because a file id in a public tracker is a working link.
        """
        # The one network call this server makes that is not to Google, and the only
        # caller that asks for it - see `describe_environment` for why it lives here
        # rather than at startup or on every error.
        env = describe_environment(check_pypi=True)
        policy = settings.policy or Policy.default()
        # `authorized` is a boolean about a file's existence, and the path is not returned:
        # a home directory is a username, and a username is more than a bug report needs.
        authorized = os.path.exists(os.path.expanduser(settings.token_path))

        report = "\n".join([
            "### Environment",
            "",
            "```",
            env.as_markdown(),
            f"{'Profile'.ljust(20)}  {settings.profile or 'default'}",
            f"{'Read scope'.ljust(20)}  {_scope_shape(policy.read)}",
            f"{'Modify scope'.ljust(20)}  {_scope_shape(policy.modify)}",
            f"{'Read-only mode'.ljust(20)}  {settings.read_only}",
            f"{'Authorized'.ljust(20)}  {authorized}",
            "```",
            "",
            *([f"> {note}" for note in env.notes] + [""] if env.notes else []),
            "### What happened",
            "",
            "<!-- What you did, what you expected, what happened instead. Include the tool",
            "     name. Do not paste document links, file ids or comment text. -->",
        ])

        title = f"[{env.server_version}] "
        # Labelled, and NOT with the demonstration's label. An issue filed from here is a
        # person who is stuck; one filed by a demo run is telemetry about the demo. Before
        # this path carried no label at all, which made an assisted report look identical
        # to a hand-written one and left the label unable to answer the only question it is
        # good for: is anybody actually blocked?
        query = urllib.parse.urlencode(
            {"title": title, "body": report, "labels": ASSISTED_REPORT_LABEL})
        return {
            "report": report,
            "issues_url": ISSUES_URL,
            "new_issue_url": f"{ISSUES_URL}/new?{query}",
            "label": ASSISTED_REPORT_LABEL,
            "server_version": env.server_version,
            "python_version": env.python_version,
            "os": env.os,
            "architecture": env.architecture,
            "mcp_sdk_version": env.mcp_sdk_version,
            "installed_via": env.installed_via,
            "profile": settings.profile,
            "read_only": settings.read_only,
            "read_scope": _scope_shape(policy.read),
            "modify_scope": _scope_shape(policy.modify),
            "authorized": authorized,
            "checklist": list(CHECKLIST),
        }

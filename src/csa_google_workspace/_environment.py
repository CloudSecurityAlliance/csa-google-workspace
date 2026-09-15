"""The facts a bug report needs, and nothing that identifies a document.

Every question asked on an issue starts the same way — which version, which Python, which OS —
and the answer is always a round trip. This collects them once so a report can arrive complete.

**What is deliberately absent is the point of the module.** This output is written to be pasted
into a *public* issue tracker, so it carries no file ids, no document titles, no email address,
no token, and no filesystem paths. A Drive file id is not a secret in the cryptographic sense
and is very much a secret in the practical one: it is a working link to a document. `Policy`
scopes are therefore reported by *shape* — unrestricted, or "3 files" — never by content.

That is the opposite choice from `describe_configuration`, which does list the ids, and rightly:
there the audience is the person asking "what am I allowed to touch?" about their own machine.
Same data, different destination, different answer.
"""
from __future__ import annotations

import itertools
import os
import platform
import sys
from dataclasses import dataclass, field

from . import __version__

ISSUES_URL = "https://github.com/CloudSecurityAlliance/csa-google-workspace/issues"

# TWO labels, because the two paths that reach that tracker are not the same kind of report and
# want opposite triage. Kept here beside ISSUES_URL rather than in either caller: where feedback
# goes, and under what name, is one fact.
#
#   DEMO_FEEDBACK_LABEL    a demonstration run reporting on ITSELF. Unprompted, nobody is
#                          blocked, and the signal is in the aggregate - twenty runs skipping
#                          the same step is a design problem, one run skipping it is a policy.
#   ASSISTED_REPORT_LABEL  a PERSON has a problem now and a model helped them describe it.
#                          Somebody is stuck. Read these first.
#
# They were one label - or rather, the demo had one and `report_a_problem` had none, which made
# an assisted report indistinguishable from a hand-written one and defeated the labelling
# entirely. `tests/test_feedback_labels.py` asserts they stay distinct.
DEMO_FEEDBACK_LABEL = "automated-feedback"
ASSISTED_REPORT_LABEL = "assisted-report"


def _os_description() -> str:
    """A one-line OS description, using the most specific source each platform offers.

    `platform.release()` alone is close to useless for a report: on macOS it gives the Darwin
    kernel version (25.6.0), which nobody recognises as the OS they are running, and on Windows
    it gives "10" for Windows 11. Both platforms expose something better, so ask for it.
    """
    system = platform.system()
    if system == "Darwin":
        release = platform.mac_ver()[0]
        return f"macOS {release}" if release else f"macOS (Darwin {platform.release()})"
    if system == "Windows":
        release, version, service_pack, _ = platform.win32_ver()
        # "10" covers Windows 11 too; the build number in platform.version() is what actually
        # distinguishes them (22000+ is 11), so keep it.
        parts = [p for p in ("Windows", release, platform.version(), service_pack) if p]
        return " ".join(parts)
    if system == "Linux":
        try:                                    # 3.10+, and absent on some minimal images
            info = platform.freedesktop_os_release()
            pretty = info.get("PRETTY_NAME")
            if pretty:
                return pretty
        except (OSError, AttributeError):
            pass
        return f"Linux {platform.release()}"
    return f"{system} {platform.release()}".strip() or "unknown"


def _package_version(name: str) -> str | None:
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version(name)
    except PackageNotFoundError:
        return None


@dataclass(frozen=True)
class Environment:
    """What is running, where. Safe to paste into a public issue."""

    server_version: str
    python_version: str
    python_implementation: str
    os: str
    architecture: str
    mcp_sdk_version: str | None
    installed_via: str
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "server_version": self.server_version,
            "python_version": self.python_version,
            "python_implementation": self.python_implementation,
            "os": self.os,
            "architecture": self.architecture,
            "mcp_sdk_version": self.mcp_sdk_version,
            "installed_via": self.installed_via,
            "notes": list(self.notes),
        }

    def as_markdown(self) -> str:
        """A block to paste under "Environment" in an issue."""
        rows = [
            ("csa-google-workspace", self.server_version),
            ("Python", f"{self.python_version} ({self.python_implementation})"),
            ("OS", self.os),
            ("Architecture", self.architecture),
            ("mcp SDK", self.mcp_sdk_version or "not installed"),
            ("Installed via", self.installed_via),
        ]
        width = max(len(label) for label, _ in rows)
        lines = [f"{label.ljust(width)}  {value}" for label, value in rows]
        return "\n".join(lines)


def _installed_via() -> str:
    """How this copy was installed, inferred from where it lives.

    Worth reporting because the routes fail differently: a pipx or uv-tool venv is isolated and
    upgrades cleanly, a shared environment can have another project's pin holding the version
    down, and an editable checkout is somebody's working tree that may not match any release.

    `uv tool` is checked because CSA standardised on uv (DEC-012) and a uv tool venv lives under
    `site-packages` like any other, so without this it reported `pip (venv)` (#447). Not false,
    but it loses the isolation fact the field exists to carry - and it sent the reader of a
    problem report hunting for a cross-project pin that cannot exist in a tool venv.

    The two layouts differ, MEASURED 2026-09-15 rather than recalled:

        POSIX    ~/.local/share/uv/tools/<pkg>/lib/python3.12/site-packages/<pkg>
        Windows  %APPDATA%/uv/tools/<pkg>/Lib/site-packages/<pkg>        (no pythonX.Y level)

    so `uv` ADJACENT to `tools` is the only part common to both. Adjacency rather than two
    separate `in` checks, because `/home/uv/projects/tools/...` is a perfectly ordinary path.

    A uv-created *project* venv (`uv venv`) is deliberately NOT special-cased: it is a venv, it
    reports as one, and the isolation story is the same. Telling it apart would mean reading
    `pyvenv.cfg`, and this module promises no filesystem access beyond its own package.

    **The residual, measured the same day by tripping over it.** Path-sniffing answers where the
    package LIVES, not how it was installed, so `UV_TOOL_DIR` (or `PIPX_HOME`) pointing somewhere
    without the giveaway segment falls through to `pip (venv)`. Confirmed: a `uv tool install`
    into a temp `UV_TOOL_DIR` reports `pip (venv)`, and the same command into the default
    location reports `uv tool`. Definitive markers do exist - a tool venv carries
    `uv-receipt.toml`, and any uv venv writes `uv = <version>` into `pyvenv.cfg` - but both are
    filesystem reads this module does not take. The existing `pipx` check has had exactly this
    limitation since it was written; this is not a new weakness, it is the same fidelity, and
    the field is a triage hint on a bug report rather than anything decisions rest on.
    """
    location = os.path.abspath(os.path.dirname(__file__))
    parts = location.replace("\\", "/").lower().split("/")
    if "pipx" in parts:
        return "pipx"
    if any(a == "uv" and b == "tools" for a, b in itertools.pairwise(parts)):
        return "uv tool"
    if any(p in ("site-packages", "dist-packages") for p in parts):
        return "pip (shared environment)" if sys.prefix == sys.base_prefix else "pip (venv)"
    return "editable checkout or source tree"


def describe_environment() -> Environment:
    """Collect the environment facts. No network, no filesystem beyond this package."""
    installed_via = _installed_via()
    notes: list[str] = []
    # A note has to be able to fire, and has to change what the reader does. This one does
    # both: a shared environment is where another project's pin silently holds this package at
    # an old version, and "upgrade first" is then the right first reply to the report. (The
    # obvious alternative - warning about a Python below the 3.10 floor - is unreachable,
    # because pip refuses the install; ruff says so too.)
    if installed_via.startswith("pip (shared"):
        # uv first (DEC-012), pipx retained: the advice is read by somebody who has a problem
        # NOW, and plenty of machines are still pipx-installed. Naming only the standard would
        # make the note useless to exactly the people most likely to hit the stale-pin case.
        notes.append("Installed into a shared environment: another project's pin can hold this "
                     "package at an old version. `uv tool install csa-google-workspace[mcp]` "
                     "isolates it (or `pipx install` on a machine not yet migrated).")
    return Environment(
        server_version=__version__,
        python_version=platform.python_version(),
        python_implementation=platform.python_implementation(),
        os=_os_description(),
        architecture=platform.machine() or "unknown",
        mcp_sdk_version=_package_version("mcp"),
        installed_via=installed_via,
        notes=notes,
    )

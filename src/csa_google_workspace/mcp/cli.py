"""Console-script entry point: one command, two modes.

    csa-google-workspace-mcp            # run the stdio server (never prompts)
    csa-google-workspace-mcp login      # interactive consent, in a real terminal

Deliberately hand-rolled argument handling rather than an argparse subparser tree: there is
exactly one verb, and the parsing must not be the interesting part of this file.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence

from . import _logging
from ._config import WorkspaceProvider, settings_from_env, startup_warnings
from .server import create_server

USAGE = """usage: csa-google-workspace-mcp [login [--force]]

  (no argument)   run the MCP server over stdio, for an MCP client to launch
  login           authorize with Google in a browser and cache the token
  login --force   authorize again even if a cached token looks usable
  demo            create real files and walk every operation, narrated
  demo --auto     the same, unattended - it is also the end-to-end test
  configure       write a working Claude Desktop config (absolute path + policy)
  configure --print   show the JSON without writing anything
  describe        print the EFFECTIVE policy - what this install may actually do
  --version       print the installed version and exit

Clients that support MCP URL elicitation (Claude Code) can authorize in-session via
the `authenticate` tool instead, with no terminal step.

environment:
  CSA_GW_TOKEN           token cache path (default ~/.csa_google_workspace/token.json)
  CSA_GW_READ_ONLY=1     refuse writes, and use a read-only credential. Read-only
                         consent is cached separately (token.readonly.json), so a
                         read-write token will NOT be reused - log in again with this
                         set. Your read-write token is left untouched.
  CSA_GW_PROFILE         a named capability set, using Drive's OWN role names:
                         reader | commenter | writer | fileOrganizer | organizer.
                         reader may change nothing; commenter may comment, reply and
                         resolve; writer adds content edits, file creation, rename/move
                         and trash - everything RECOVERABLE; fileOrganizer adds editing
                         and deleting comments and deleting content, which Google gives
                         no way to undo; organizer adds sharing. `editor` and `full` are
                         accepted as aliases of writer and organizer.
                         UNSET MEANS NO PROFILE - not a safe middle. See below.
  CSA_GW_CAPABILITIES    which mutations are permitted - the complete list, not a delta.
                         UNSET MEANS EVERYTHING IS ON: all eleven capabilities,
                         including the four Google gives no way to undo (comment.edit,
                         comment.delete, content.delete, file.share). Narrowing is what
                         you configure. Tokens: any capability name, plus `default`,
                         `all`, `none`.
                           default,file.trash          the usual set, plus trashing
                           comment.create,comment.reply  exactly these two
                           none                        no mutation at all
  CSA_GW_ALLOWLIST_READ    which files may be READ
  CSA_GW_ALLOWLIST_MODIFY  which files may be CHANGED, added to, or deleted

                         UNSET MEANS EVERY FILE the credentials can reach. What fails
                         closed is a list you TRIED to write: one bad line, or a list
                         with no usable entries, refuses and the server does not start.
                         Each holds either `*` or the document URLs themselves - there
                         is no allowlist file, and a path-shaped value is reported as a
                         mistake rather than read.

                         The usual posture:
                           CSA_GW_ALLOWLIST_READ=*
                           CSA_GW_ALLOWLIST_MODIFY=https://docs.google.com/document/d/AAA/edit

                         Entries are separated by newlines or commas; `#` starts a
                         comment and the comment is the reason. A value of just `*` means
                         every file. Anything unusable is a hard failure, never a
                         fallback to unrestricted access, and the error says which kind
                         of mistake it was. Folders are not supported yet and are
                         rejected loudly.
  CSA_GW_CLIENT_SECRETS  OAuth client secrets JSON (`login` only; defaults to
                         ~/.csa_google_workspace/client_secret.json if that exists)
"""


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    env = os.environ if env is None else env
    # Before anything else that might log, and here rather than in the library: only an
    # application configures logging. See _logging for why this is twenty lines and not a
    # subsystem - the client already persists our stderr.
    _logging.configure(env)
    settings = settings_from_env(env)

    if argv and argv[0] in ("-h", "--help", "help"):
        print(USAGE, file=sys.stderr)      # stderr: stdout belongs to JSON-RPC
        return 0
    if argv and argv[0] in ("--version", "-V", "version"):
        # Also on stderr, for the same reason as USAGE. The version was previously reachable
        # only by starting a session and calling describe_configuration, which means an
        # installer could not check what it had just installed -- and a pipx upgrade that
        # silently changed nothing looked identical to one that worked. This is the answer to
        # "which version is actually on this machine?" without an MCP client in the loop.
        from .. import __version__
        print(__version__, file=sys.stderr)
        return 0
    if argv and argv[0] in ("describe", "describe-configuration", "config"):
        # The same text as the `csa-gw://config` resource and the `describe_configuration`
        # tool, reachable WITHOUT an MCP client — for the same reason `--version` exists: an
        # installer could not otherwise check what it had just configured.
        #
        # It was needed for a specific bug. The CSA installer printed a notice saying what had
        # just been granted, hardcoded to the DEFAULT posture — and when it kept a user's
        # existing environment instead of writing one, the notice described a config they did
        # not have. It told somebody sharing was off while `file.share` was enabled. A notice
        # about permissions has to be generated from the permissions, not from an assumption
        # about them.
        from ._resources import render_config
        print(render_config(settings), file=sys.stderr)
        return 0
    if argv and argv[0] in ("configure", "configure-desktop"):
        # D2. Claude Desktop is a GUI app, so on macOS it inherits launchd's PATH -
        # /usr/bin:/bin:/usr/sbin:/sbin - which has neither ~/.local/bin nor Homebrew, and
        # whose `python3` is macOS's 3.9, below our floor. The README documented the fix (an
        # absolute path) for months, which asked the user to know their own home directory and
        # hand-edit shared JSON. This writes it instead.
        from ._desktop import config_path, configure, launch_command
        rest = argv[1:]
        show_only = bool(rest) and rest[0] in ("--print", "--dry-run", "-n")
        if rest and not show_only:
            print(f"unknown argument: {rest[0]}\n\n{USAGE}", file=sys.stderr)
            return 2
        command, how = launch_command()
        try:
            result = configure(env=env, dry_run=show_only)
        except ValueError as e:
            print(f"csa-google-workspace: {e}", file=sys.stderr)
            return 1
        out = sys.stderr                     # stderr for the same reason as USAGE
        print(f"command: {' '.join(command)}\n  ({how})", file=out)
        if show_only:
            print(f"\nwould write to {config_path(env)}:\n{result.rendered}", file=out)
            return 0
        if result.created:
            print(f"created {result.path}", file=out)
        elif result.changed:
            print(f"updated {result.path}", file=out)
            # Unconditional, because `configure` takes a backup on exactly this condition -
            # the file existed and its contents are changing - so a guard on `result.backup`
            # here is a branch that cannot be false. Coverage is what said so: it sat as a
            # partial branch, which is the dead-code signal rather than a gap in testing.
            print(f"previous version kept at {result.backup}", file=out)
        else:
            print(f"{result.path} was already correct", file=out)
        from ._desktop import carried_env
        carried = carried_env(env)
        if carried:
            print(f"carried {len(carried)} CSA_GW_* variable(s) into the env block "
                  f"({', '.join(carried)}) - Claude Desktop has no shell, so this is the "
                  f"only place it reads them", file=out)
        else:
            # This told the operator the OPPOSITE of runtime behaviour, at the moment they
            # set the server up - "nothing is reachable until you set CSA_GW_ALLOWLIST_READ"
            # when in fact everything is. Found as RR-003, 2026-09-01. A wrong sentence in a
            # file nobody opens is a defect; a wrong sentence printed during setup is somebody
            # believing they are scoped when they are not.
            print("no CSA_GW_* variables set here, so none were carried - Desktop will use "
                  "THE DEFAULTS, WHICH ARE OPEN: every capability on, and both allowlists "
                  "permitting every file this account can reach. Narrowing is what you "
                  "configure - set CSA_GW_READ_ONLY=1 for the narrowest useful posture, or "
                  "CSA_GW_PROFILE / CSA_GW_ALLOWLIST_MODIFY to scope it. Run `describe` to "
                  "see what an install actually permits.", file=out)
        print("restart Claude Desktop for this to take effect", file=out)
        return 0
    if argv and argv[0] == "demo":
        # A guided demonstration that is also this project's end-to-end test - see
        # csa_google_workspace.demo. Imported here so the server path never loads it.
        from ..demo._cli import main as demo_main
        return demo_main(argv[1:], env)
    if argv and argv[0] == "login":
        from ._login import login  # imported here so the server path never loads it
        rest = argv[1:]
        force = bool(rest) and rest[0] in ("--force", "-f", "--reauth")
        if rest and not force:
            print(f"unknown argument: {rest[0]}\n\n{USAGE}", file=sys.stderr)
            return 2
        return login(settings, env, force=force)
    if argv:
        print(f"unknown argument: {argv[0]}\n\n{USAGE}", file=sys.stderr)
        return 2

    # stderr, never stdout: stdout is the JSON-RPC channel and a single stray byte on it
    # corrupts the session. Most MCP clients surface a server's stderr in their logs, which
    # is the only place to say this before the first tool call.
    for line in startup_warnings(settings):
        print(f"csa-google-workspace: {line}", file=sys.stderr)

    # The server never resolves credentials here: a missing token must not stop the server
    # from starting, or the MCP client reports an opaque "server failed to start" and the
    # user never sees the remedy. Tools surface it instead, where it is readable.
    create_server(WorkspaceProvider(settings), settings=settings).run(transport="stdio")
    return 0

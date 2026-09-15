"""D2: make Claude Desktop work, instead of documenting why it does not.

The failure, which is macOS-specific and unavoidable: **Claude Desktop is a GUI app**, so it
inherits launchd's `PATH` — `/usr/bin:/bin:/usr/sbin:/sbin`. That contains neither `~/.local/bin`
(where `pipx` puts the console script) nor Homebrew, and the `python3` it does contain is macOS's
system 3.9, below this package's 3.10 floor. So a bare command name is not found, and `python3` is
the wrong interpreter. Claude Code, running in your shell, works fine — which makes this look like
a Desktop bug rather than a `PATH` fact.

The README has documented the fix for months: put the **absolute path** in
`claude_desktop_config.json`. That was not a fix, it was a workaround with a hand-edit in it —
the user has to know their own home directory, produce valid JSON, and not clobber the other
servers already in that file. Half the intended clients are Desktop.

So the tool writes it. It knows its own absolute path; the user should not have to.

There is a second half people hit immediately after the first: **Desktop has no shell**, so the
policy environment variables that work in a terminal are simply absent. `configure` carries the
CSA_GW_* variables from the environment it runs in into the config's `env` block, which is the
only place Desktop will read them.
"""
from __future__ import annotations

import json
import os

import pytest

from csa_google_workspace.mcp import _desktop


@pytest.fixture
def config(tmp_path):
    return tmp_path / "claude_desktop_config.json"


class TestTheCommandItWrites:
    def test_it_is_an_absolute_path(self):
        """The whole point. A bare name is what fails under launchd's PATH."""
        command, _ = _desktop.launch_command()
        # `os.path.isabs`, not `startswith("/")`: an absolute Windows path is `C:\...`, so the
        # POSIX spelling of "absolute" failed here while the production code was correct. (#453)
        assert os.path.isabs(command[0])

    def test_it_does_not_use_a_bare_python3(self):
        """`python3` on the GUI PATH is macOS's 3.9, below the 3.10 floor - so even a
        correctly-located module invocation fails if the interpreter is the system one."""
        command, _ = _desktop.launch_command()
        assert command[0] != "python3"
        assert not command[0].endswith("/usr/bin/python3")


class TestWritingTheConfig:
    def test_it_creates_the_file_when_absent(self, config):
        _desktop.configure(config, env={})
        written = json.loads(config.read_text(encoding="utf-8"))
        assert "csa-google-workspace" in written["mcpServers"]
        assert os.path.isabs(written["mcpServers"]["csa-google-workspace"]["command"])

    def test_it_keeps_other_servers(self, config):
        """The file is shared. Overwriting it would remove every other MCP server the user
        has configured, which is a far worse outcome than the problem being fixed."""
        config.write_text(json.dumps({"mcpServers": {"other": {"command": "/bin/other"}}}))
        _desktop.configure(config, env={})
        written = json.loads(config.read_text())
        assert written["mcpServers"]["other"] == {"command": "/bin/other"}
        assert "csa-google-workspace" in written["mcpServers"]

    def test_it_keeps_unrelated_top_level_keys(self, config):
        config.write_text(json.dumps({"globalShortcut": "Cmd+X", "mcpServers": {}}))
        _desktop.configure(config, env={})
        assert json.loads(config.read_text())["globalShortcut"] == "Cmd+X"

    def test_it_backs_up_what_it_replaces(self, config):
        config.write_text(json.dumps({"mcpServers": {"other": {"command": "/bin/other"}}}))
        _desktop.configure(config, env={})
        backups = list(config.parent.glob("claude_desktop_config.json.bak*"))
        assert backups, "a config the user may have hand-written was replaced with no backup"
        assert "other" in backups[0].read_text()

    def test_it_is_idempotent(self, config):
        _desktop.configure(config, env={})
        first = config.read_text()
        _desktop.configure(config, env={})
        assert json.loads(config.read_text()) == json.loads(first)

    def test_malformed_json_is_refused_not_overwritten(self, config):
        """Somebody's hand-edited file with a trailing comma is not a file to silently
        replace - it is a file they are in the middle of editing."""
        config.write_text("{ not json")
        with pytest.raises(ValueError, match="could not be read|not valid JSON"):
            _desktop.configure(config, env={})
        assert config.read_text() == "{ not json"


class TestCarryingThePolicy:
    def test_csa_variables_are_carried_into_the_env_block(self, config):
        """Desktop has no shell, so a variable that works in a terminal is absent there. This
        is the only place it can be stated."""
        _desktop.configure(config, env={"CSA_GW_ALLOWLIST_READ": "*",
                                        "CSA_GW_PROFILE": "commenter"})
        block = json.loads(config.read_text())["mcpServers"]["csa-google-workspace"]["env"]
        assert block["CSA_GW_ALLOWLIST_READ"] == "*"
        assert block["CSA_GW_PROFILE"] == "commenter"

    def test_unrelated_variables_are_not_carried(self, config):
        """It reads the ambient environment, so it must copy only what it owns - not the
        user's whole shell, which holds tokens and paths that have no business in a config
        file somebody may screenshot."""
        _desktop.configure(config, env={"CSA_GW_PROFILE": "reader", "AWS_SECRET_ACCESS_KEY": "x",
                                        "PATH": "/whatever", "GITHUB_TOKEN": "ghp_x"})
        block = json.loads(config.read_text())["mcpServers"]["csa-google-workspace"]["env"]
        assert set(block) == {"CSA_GW_PROFILE"}

    def test_the_client_secrets_variable_is_not_carried(self, config):
        """`login` needs it; the running server never does - a cached token carries its own
        client id and secret. Writing it into a config file spreads a credential path for no
        benefit."""
        _desktop.configure(config, env={"CSA_GW_CLIENT_SECRETS": "/home/me/secret.json",
                                        "CSA_GW_PROFILE": "reader"})
        block = json.loads(config.read_text())["mcpServers"]["csa-google-workspace"]["env"]
        assert "CSA_GW_CLIENT_SECRETS" not in block

    def test_no_env_block_when_there_is_nothing_to_carry(self, config):
        _desktop.configure(config, env={})
        entry = json.loads(config.read_text())["mcpServers"]["csa-google-workspace"]
        assert "env" not in entry or entry["env"] == {}


class TestTheDryRun:
    def test_it_writes_nothing(self, config):
        _desktop.configure(config, env={}, dry_run=True)
        assert not config.exists()

    def test_it_still_reports_what_it_would_do(self, config):
        result = _desktop.configure(config, env={}, dry_run=True)
        assert "csa-google-workspace" in result.rendered
        assert result.path == config

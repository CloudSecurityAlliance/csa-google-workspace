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
import stat
import sys

import pytest

from csa_google_workspace.mcp import _desktop


@pytest.fixture
def config(tmp_path):
    return tmp_path / "claude_desktop_config.json"



def _console_script(directory):
    """Create the console script the way the platform actually ships it.

    The fixtures used to write `SCRIPT_NAME` with no suffix, so `Path.exists()` found exactly
    that name on Windows and the test passed while the real install — which carries `.exe` —
    failed. Same blind spot as csa-zendesk#80: the code and the fixture shared one wrong
    assumption, so the suite confirmed the bug instead of catching it.

    The exec bit matters on POSIX because `shutil.which` requires it, unlike `exists()`.
    """
    name = _desktop.SCRIPT_NAME + (".exe" if sys.platform == "win32" else "")
    path = directory / name
    path.write_text("#!/usr/bin/env python3\n")
    if sys.platform != "win32":
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


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


class TestWhereTheConfigLives:
    """`config_path` per platform. Only one branch can run on any given machine, so the other
    two had never executed - and the Windows one is the branch that matters most, because
    Desktop on Windows is half the intended audience and `Path.home()/AppData` is not where it
    looks if `APPDATA` has been redirected."""

    def test_macos_uses_application_support(self, monkeypatch):
        monkeypatch.setattr(_desktop.sys, "platform", "darwin")
        assert _desktop.config_path({}) == (
            _desktop.Path.home() / "Library/Application Support/Claude/claude_desktop_config.json")

    def test_windows_prefers_the_appdata_variable_over_a_guess(self, monkeypatch):
        """A roaming profile, a redirected AppData, or a machine where the user directory is
        not under `C:\\Users` - all of them move this, and `APPDATA` is the value that is
        actually right. Guessing from the home directory is the fallback, not the answer."""
        monkeypatch.setattr(_desktop.sys, "platform", "win32")
        got = _desktop.config_path({"APPDATA": "D:/Roaming"})
        assert got == _desktop.Path("D:/Roaming") / "Claude/claude_desktop_config.json"

    @pytest.mark.parametrize("env", [{}, {"APPDATA": ""}], ids=["unset", "empty"])
    def test_windows_without_appdata_falls_back_under_the_home_directory(self, monkeypatch, env):
        """An empty string counts as unset. `Path("") / "Claude/..."` is a RELATIVE path, so
        taking it literally would write the config into the current working directory."""
        monkeypatch.setattr(_desktop.sys, "platform", "win32")
        expected = _desktop.Path.home() / "AppData/Roaming/Claude/claude_desktop_config.json"
        assert _desktop.config_path(env) == expected

    def test_linux_answers_rather_than_raising(self, monkeypatch):
        """Linux Desktop is not a shipped target. Returning the XDG-ish location is more
        useful than an exception, because `configure --print` still shows somebody the right
        JSON to paste - which is the whole of what this can do for them there."""
        monkeypatch.setattr(_desktop.sys, "platform", "linux")
        assert _desktop.config_path({}) == (
            _desktop.Path.home() / ".config/Claude/claude_desktop_config.json")

    def test_it_reads_the_process_environment_when_given_none(self, monkeypatch):
        monkeypatch.setattr(_desktop.sys, "platform", "win32")
        monkeypatch.setenv("APPDATA", "E:/Elsewhere")
        assert _desktop.config_path() == (
            _desktop.Path("E:/Elsewhere") / "Claude/claude_desktop_config.json")


class TestResolvingTheLaunchCommand:
    """Three sources, in order of how self-contained the result is. Only the first runs in a
    normal checkout, so the two fallbacks had never executed - and they are what a `pipx`
    install that has been moved, or a `python -m` invocation, actually lands on."""

    def test_the_script_beside_this_interpreter_wins(self, tmp_path, monkeypatch):
        """A pipx or venv install. The script's shebang pins the correct Python, so the config
        needs no interpreter and no PATH - which is the entire problem being solved."""
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        script = _console_script(fake_bin)
        monkeypatch.setattr(_desktop.sys, "executable", str(fake_bin / "python"))

        # The guard is kept and sharpened. It used to fail on ANY which() call, which stopped
        # being right when branch 1 started using which() itself (#511) - the thing worth
        # forbidding is consulting the AMBIENT PATH before the local script, so that is what
        # is asserted: the first call must name a directory.
        real_which = _desktop.shutil.which
        calls = []

        def spy(name, path=None):
            calls.append(path)
            if path is None:
                pytest.fail("the ambient PATH was consulted before the local script")
            return real_which(name, path=path)

        monkeypatch.setattr(_desktop.shutil, "which", spy)

        command, how = _desktop.launch_command()
        assert command == [str(script.resolve())]
        assert "beside this interpreter" in how
        assert calls == [str(fake_bin)], calls
        if sys.platform == "win32":
            assert command[0].lower().endswith(".exe")

    def test_a_script_on_path_is_resolved_to_an_absolute_path(self, tmp_path, monkeypatch):
        """Correct, and one step less certain - it may not be the install this process came
        from, which is why the reason is reported alongside. Resolved because a bare name is
        exactly what fails under launchd's PATH."""
        elsewhere = tmp_path / "usr" / "local" / "bin"
        elsewhere.mkdir(parents=True)
        script = _console_script(elsewhere)
        monkeypatch.setattr(_desktop.sys, "executable", str(tmp_path / "nowhere" / "python"))
        # `path=None` is branch 2 (the ambient PATH); a named path is branch 1, which finds
        # nothing here because sys.executable points at an empty directory.
        monkeypatch.setattr(_desktop.shutil, "which",
                            lambda n, path=None: None if path else str(script))

        command, how = _desktop.launch_command()
        assert command == [str(script.resolve())]
        assert _desktop.Path(command[0]).is_absolute()
        assert _desktop.SCRIPT_NAME in how and "PATH" in how

    def test_the_last_resort_is_this_interpreter_with_dash_m(self, tmp_path, monkeypatch):
        """Always available and always right about the interpreter - `sys.executable` is
        absolute by construction - which is what makes it a real fallback rather than a
        guess."""
        monkeypatch.setattr(_desktop.sys, "executable", str(tmp_path / "nowhere" / "python"))
        monkeypatch.setattr(_desktop.shutil, "which", lambda n, path=None: None)

        command, how = _desktop.launch_command()
        assert command == [str(tmp_path / "nowhere" / "python"), "-m", "csa_google_workspace.mcp"]
        assert "-m" in how

    def test_a_multi_word_command_is_split_into_command_and_args(self, tmp_path, monkeypatch):
        """Claude Desktop's config has separate `command` and `args` keys; putting
        "python -m csa_google_workspace.mcp" in `command` makes it look for an executable with
        spaces in its name."""
        monkeypatch.setattr(_desktop.sys, "executable", str(tmp_path / "nowhere" / "python"))
        monkeypatch.setattr(_desktop.shutil, "which", lambda n, path=None: None)

        written = _desktop.entry({})
        assert written["command"] == str(tmp_path / "nowhere" / "python")
        assert written["args"] == ["-m", "csa_google_workspace.mcp"]

    def test_a_single_word_command_carries_no_args_key_at_all(self, tmp_path, monkeypatch):
        """Absent rather than empty. `"args": []` is a different document, and this file is
        diffed against itself to decide whether anything changed."""
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        _console_script(fake_bin)
        monkeypatch.setattr(_desktop.sys, "executable", str(fake_bin / "python"))

        assert "args" not in _desktop.entry({})


def test_a_config_that_is_not_a_json_object_is_left_alone(tmp_path):
    """Valid JSON, wrong shape - a list, a string, a number. It parses, so the JSONDecodeError
    branch does not catch it, and `existing.get` would raise AttributeError deep inside the
    merge. Somebody's other MCP servers are not in there, but whatever IS in there is theirs."""
    path = tmp_path / "claude_desktop_config.json"
    path.write_text('["not", "an", "object"]', encoding="utf-8")

    with pytest.raises(ValueError, match="could not be read as a JSON object"):
        _desktop.configure(path, env={})
    assert path.read_text() == '["not", "an", "object"]'

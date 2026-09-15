"""The desktop config is written `0600`, and its backups do not accumulate forever.

`claude_desktop_config.json` was written with `path.write_text(rendered)` — no explicit mode, so
whatever the umask gives, typically `0644`. And every changed run snapshotted the previous
version to `.bak.<stamp>`, never pruned.

**No secret value lands there**, and that is deliberate: `CSA_GW_CLIENT_SECRETS` is excluded by
`carried_env()` with the reasoning written down. What *does* land is:

  * `CSA_GW_TOKEN`, which points any local reader straight at the full-Drive token, and
  * the allowlisted document URLs, which are the policy itself.

So the file is a map to the credential and a statement of what may be touched. World-readable is
the wrong default for that, and each stale `.bak` preserves **a policy the operator believes they
have since tightened** — which is the worse half: an old backup is not merely clutter, it is a
record contradicting the current intent, sitting next to it, with an older timestamp.

**Backups are capped rather than dropped.** They exist because a second run must not destroy the
copy of a file somebody hand-wrote, and that reason survives; what does not survive is keeping
every one of them since installation.
"""
from __future__ import annotations

import json
import os

from csa_google_workspace import auth
from csa_google_workspace.mcp import _desktop


def owner_only(path):
    """Asked as a question, not as `0o600`.

    `0o600` is the POSIX *answer*. On Windows `chmod` moves only the read-only bit, so the mode
    literal answered `0o666` forever while the file was genuinely unprotected - the same gap
    #451 found in the token writer, in a file that is a map to that very token. (#453)
    """
    return auth.file_is_owner_only(str(path))


def existing_config(path, servers=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcpServers": servers or {"other": {"command": "x"}}}),
                    encoding="utf-8")
    return path


def configure(path, **kw):
    return _desktop.configure(path=path,
                              env={"CSA_GW_TOKEN": "/home/u/.csa/token.json",
                                   "CSA_GW_PROFILE": "editor"}, **kw)


class TestTheConfigIsNotWorldReadable:
    def test_a_newly_created_config_is_owner_only(self, tmp_path):
        path = tmp_path / "claude_desktop_config.json"
        configure(path)
        assert owner_only(path) is True, (
            "config is readable beyond its owner; it names the token path and the allowlist")

    def test_an_existing_config_is_tightened_too(self, tmp_path):
        """Somebody who ran an older version already has a 0644 file. Rewriting it is the only
        chance to fix that, and skipping it would leave the exposure in place for exactly the
        people who have been using this longest."""
        path = existing_config(tmp_path / "claude_desktop_config.json")
        if os.name != "nt":
            path.chmod(0o644)
        configure(path)
        assert owner_only(path) is True

    def test_the_backup_is_owner_only_as_well(self, tmp_path):
        """A backup of a sensitive file is a sensitive file. `shutil.copy2` preserves the
        SOURCE's mode, so a previously-0644 config produced a 0644 backup."""
        path = existing_config(tmp_path / "claude_desktop_config.json")
        if os.name != "nt":
            path.chmod(0o644)
        result = configure(path)
        assert result.backup is not None, "precondition: an existing changed file is backed up"
        assert owner_only(result.backup) is True

    def test_a_dry_run_writes_nothing_at_all(self, tmp_path):
        path = tmp_path / "claude_desktop_config.json"
        configure(path, dry_run=True)
        assert not path.exists()


class TestBackupsAreCappedNotUnbounded:
    def _bak(self, tmp_path):
        return sorted(p.name for p in tmp_path.iterdir() if ".bak." in p.name)

    def test_repeated_changed_runs_do_not_accumulate_forever(self, tmp_path, monkeypatch):
        path = existing_config(tmp_path / "claude_desktop_config.json")
        stamps = iter(f"2026010{i}-000000" for i in range(1, 10))
        monkeypatch.setattr(_desktop.time, "strftime", lambda *_a, **_k: next(stamps))
        for n in range(8):
            existing_config(path, servers={"other": {"command": f"x{n}"}})
            configure(path)
        kept = self._bak(tmp_path)
        assert len(kept) <= _desktop.KEEP_BACKUPS, (
            f"{len(kept)} backups kept; each one preserves a policy the operator believes they "
            f"have since tightened")

    def test_the_newest_are_the_ones_kept(self, tmp_path, monkeypatch):
        """Pruning the wrong end would throw away the only copy of what the user just had."""
        path = existing_config(tmp_path / "claude_desktop_config.json")
        stamps = iter(f"2026010{i}-000000" for i in range(1, 10))
        monkeypatch.setattr(_desktop.time, "strftime", lambda *_a, **_k: next(stamps))
        for n in range(8):
            existing_config(path, servers={"other": {"command": f"x{n}"}})
            configure(path)
        kept = self._bak(tmp_path)
        assert kept == sorted(kept)[-len(kept):]
        assert kept[-1].endswith("20260108-000000"), f"newest not kept: {kept}"

    def test_one_backup_is_still_taken(self, tmp_path):
        """The reason backups exist survives the cap: a second run must not destroy the copy of
        a file somebody hand-wrote."""
        path = existing_config(tmp_path / "claude_desktop_config.json")
        result = configure(path)
        assert result.backup is not None and result.backup.exists()

    def test_no_backup_when_nothing_changed(self, tmp_path):
        path = existing_config(tmp_path / "claude_desktop_config.json")
        configure(path)
        second = configure(path)
        assert second.backup is None, "an unchanged run should not churn backups"


class TestTheClientSecretStillNeverLandsThere:
    """Guarding the thing that was already right, since this file is now being edited."""

    def test_the_secret_path_is_not_carried(self):
        carried = _desktop.carried_env({"CSA_GW_CLIENT_SECRETS": "/secret.json",
                                        "CSA_GW_TOKEN": "/t.json",
                                        "CSA_GW_PROFILE": "editor"})
        assert "CSA_GW_CLIENT_SECRETS" not in carried
        assert carried == {"CSA_GW_TOKEN": "/t.json", "CSA_GW_PROFILE": "editor"}

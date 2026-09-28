"""Suite-wide guards that have to hold for every test, including ones not yet written.

**HOME is redirected for the whole suite.** This package's defaults all hang off the home
directory - `~/.csa_google_workspace/token.json`, `~/.csa_google_workspace/client_secret.json`,
and on macOS `~/Library/Application Support/Claude/claude_desktop_config.json`. A test that
exercises a default path therefore writes to the developer's real machine, and the two worst
cases are not hypothetical: `configure` MERGES into the live Claude Desktop config (keeping a
timestamped backup of it), and `login` writes a real credential.

The sibling `csa-google-gmail-calendar` learned this the expensive way - a test created a
directory under the real `~/Documents`, and finding it took bisecting the suite file by file,
because nothing in the failing test mentioned a home directory. The fix belongs here rather
than in the test that happens to need it, since the next such test will not know to ask.

Autouse and session-independent: no test opts in, so none can forget.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _home_is_disposable(tmp_path_factory, monkeypatch):
    """Point HOME (and Windows' USERPROFILE) at a per-test directory.

    `Path.home()` and `os.path.expanduser` both read these, which covers every way this
    package resolves a default path. The directory exists, so code that checks before writing
    still takes its normal branch - the goal is a real home that is disposable, not a missing
    one, since an absent HOME exercises a path no user has.

    `tmp_path_factory`, NOT `tmp_path`: several tests assert that an operation left no stray
    files beside its output by listing `tmp_path`, and a home directory planted inside it
    reads as exactly such a stray. The home is a sibling of the test's own tmp_path, not a
    child of it.
    """
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home

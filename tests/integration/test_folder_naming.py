"""Naming of the folder the live suite creates its throwaway files in.

**Offline, and it lives HERE rather than in `tests/` for an import reason worth knowing.**
`tests/` has no `__init__.py`, so `tests.integration.…` resolves only when the repo root
happens to be on `sys.path` — true locally, false under CI's invocation, which is where the
first version of this file died with `ModuleNotFoundError: No module named 'tests'`.
`tests/integration/` *is* a package, so pytest imports these modules as `integration.<name>`
and a **relative** import from a sibling always works.

It carries no `CSA_GW_INTEGRATION` gate on purpose: the naming logic is the part that decides
*where somebody's Drive gets written to*, and it should not need credentials to be checked.
The live suite beside it stays gated.

**Drive does not enforce unique names.** Creating a folder never overwrites one — it quietly
makes a second folder with the same name. So the check is not about overwriting. It is about
never adopting a folder somebody else made, and never leaving two identically-named folders
with no way to tell which run owned which.
"""
from __future__ import annotations

import datetime
import re

from .test_all_types_live import _folder_named, _free_folder_name

WHEN = datetime.datetime(2026, 9, 5, 21, 47, tzinfo=datetime.UTC)


class _Files:
    """Just enough of `FileCollection` to answer the one query this code makes."""

    def __init__(self, taken: list[str]):
        self.taken = set(taken)
        self.queries: list[str] = []

    def search(self, query: str, limit: int = 25):
        self.queries.append(query)
        m = re.search(r"name = '((?:[^'\\]|\\.)*)'", query)
        assert m, f"the query does not carry a quoted name: {query}"
        name = m.group(1).replace("\\'", "'").replace("\\\\", "\\")
        return [object()] if name in self.taken else []


class _WS:
    def __init__(self, taken: list[str] | None = None):
        self.files = _Files(taken or [])


def test_the_default_name_is_the_dated_pattern():
    assert _free_folder_name(_WS(), WHEN) == "csa-google-workspace-202609052147"


def test_a_taken_name_is_never_reused():
    """The point of looking first. Reuse would mean writing into a folder we did not create."""
    ws = _WS(["csa-google-workspace-202609052147"])
    assert _free_folder_name(ws, WHEN) == "csa-google-workspace-202609052147-2"


def test_it_keeps_counting_past_the_first_suffix():
    ws = _WS(["csa-google-workspace-202609052147", "csa-google-workspace-202609052147-2"])
    assert _free_folder_name(ws, WHEN) == "csa-google-workspace-202609052147-3"


def test_it_only_matches_folders_and_only_untrashed_ones():
    ws = _WS()
    _free_folder_name(ws, WHEN)
    q = ws.files.queries[0]
    assert "mimeType = 'application/vnd.google-apps.folder'" in q, "would match FILES too"
    # `FileCollection.search` appends `trashed = false` unless the query mentions trashed, so
    # naming it here would DISABLE that. The absence is load-bearing, not an omission.
    assert "trashed" not in q


def test_a_quote_in_an_existing_name_cannot_break_the_query():
    """An apostrophe is legal in a Drive folder name and terminates a `q` string literal.

    Unescaped, `kurt's folder` makes the query invalid — Google answers 400, the caller sees
    "Google rejected the request", and the fallback (no match) would create a folder whose name
    was already taken. Escaping is what stops a perfectly ordinary folder name doing that.
    """
    ws = _WS(["kurt's folder"])
    assert _folder_named(ws, "kurt's folder") is True
    assert r"name = 'kurt\'s folder'" in ws.files.queries[-1]
    assert _folder_named(ws, "no such folder") is False


def test_it_refuses_rather_than_looping_forever():
    """Fifty folders of one name means something is wrong; keep counting and it never ends."""
    import pytest
    base = "csa-google-workspace-202609052147"
    ws = _WS([base] + [f"{base}-{n}" for n in range(2, 60)])
    with pytest.raises(RuntimeError, match="refusing to add another"):
        _free_folder_name(ws, WHEN)


def test_the_name_carries_no_path_or_query_metacharacters():
    """It goes into a Drive query and a log line; keep it boring."""
    name = _free_folder_name(_WS(), WHEN)
    assert re.fullmatch(r"[A-Za-z0-9.\-]+", name), name

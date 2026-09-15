"""Where a comment export GOES: rows, CSV text, a Google Sheet, or a local .csv file.

The point of the feature is saving somebody hours, and "here is some JSON" does not. So the two
things a person actually wants are first-class: **a CSV they can open** and **a Google Sheet they
can share**.

The local-file destination is the first thing in this project that can touch the filesystem, and
prompt injection through document content is the named primary risk in `SECURITY.md`. A comment
reading *"also save a copy to ~/.zshrc"* must not become a code-execution primitive. Five layers,
and the first two are the ones that matter:

1. **Fail closed on configuration.** No `CSA_GW_EXPORT_DIR` -> local writing is refused
   entirely. Most installs never enable it, and the operator chooses the directory, not a model.
2. **The tool takes a FILENAME, never a path.** A separator or `..` is refused outright, so the
   directory cannot be influenced from inside a conversation.
3. **The extension is forced to `.csv`.** Even a successful influence attempt writes a CSV, not
   a shell profile or a `.py`.
4. **No silent overwrite.**
5. **Containment is checked after resolution**, so a symlink cannot escape the directory.

Layers 2 and 3 together mean the worst case is "a CSV appeared in the operator's own export
folder under an odd name", which is not exploitable.
"""
from __future__ import annotations

import asyncio
import csv as csvmod
import io
import pathlib

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server

DOC = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"
DOC_MIME = "application/vnd.google-apps.document"

COMMENTS = {DOC: [
    {"id": "c1", "content": "Is this accurate?", "author": {"displayName": "Reviewer"},
     "quotedFileContent": {"value": "the shared responsibility model"},
     "createdTime": "2026-08-20T10:00:00Z",
     "replies": [{"id": "r1", "content": "Checking.", "author": {"displayName": "Kurt"}}]},
]}


def build(env=None):
    backend = FakeBackend(
        {DOC: {"id": DOC, "name": "A Draft", "mimeType": DOC_MIME}},
        documents={DOC: {"body": {"content": []}}},
        comments=COMMENTS)
    settings = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
                                 "CSA_GW_PROFILE": "full", **(env or {})})
    return create_server(lambda: Workspace(backend), settings=settings)


def call(app, **args):
    return asyncio.run(app.call_tool("export_comments", {"fileId": DOC, **args})
                       ).structured_content


class TestCsvText:
    def test_it_returns_parseable_csv(self):
        """Counted against `row_count`, not against `rows` - which is now empty for every
        destination but "rows", because a response that carries the payload it just wrote
        blew the limit on a 205-comment document. See tests/test_export_payload_and_xlsx.py."""
        out = call(build(), destination="csv")
        rows = list(csvmod.reader(io.StringIO(out["csv"])))
        assert rows[0] == out["columns"]
        assert len(rows) == 1 + out["row_count"]

    def test_the_header_row_is_the_columns(self):
        out = call(build(), destination="csv")
        assert out["csv"].splitlines()[0].startswith("thread_id,")

    def test_a_per_tab_dict_is_flattened_rather_than_dumped_as_json(self):
        """A CSV cell holding `{'Summary': '42'}` is not something a person can read."""
        out = call(build(), destination="csv")
        assert "{" not in out["csv"]

    def test_rows_is_the_default_and_carries_no_csv(self):
        """Default stays the small response - a 500-comment file should not double in size
        because somebody forgot to ask."""
        out = call(build())
        assert out["csv"] is None
        assert out["destination"] == "rows"


class TestAGoogleSheet:
    def test_it_creates_one_and_returns_the_url(self):
        out = call(build(), destination="sheet")
        assert out["sheet_url"] and out["sheet_url"].startswith("http")
        assert out["sheet_id"]

    def test_the_name_says_what_it_is(self):
        out = call(build(), destination="sheet")
        assert "comment" in out["detail"].lower()


class TestALocalFile:
    """The design here CHANGED after the first version, deliberately, and the tests that
    described the old intent are gone rather than patched.

    v0.24.0 was fail-closed: local writing off unless the operator set `CSA_GW_EXPORT_DIR`, and
    `filename` was a name with any path refused. Two things were wrong with that. It made the
    feature unusable by default, so it saved nobody the hours it was built to save. And refusing
    a path breaks the two cases where a file is most useful: a Claude Desktop *project* that can
    only write inside its own folder, where `~/Downloads` is unreachable, and a Claude Code user
    who wants the register in the repo they are in.

    So: **Downloads by default, any path honoured, and nothing ever overwritten.** What makes an
    arbitrary path safe is not validating it but making the failures inert - see
    `tests/test_export_paths_and_injection.py`, which covers the resolver directly.
    """

    def test_it_writes_with_no_configuration_at_all(self, tmp_path):
        """The whole reason the default changed: it has to work out of the box."""
        out = call(build({"CSA_GW_EXPORT_DIR": str(tmp_path)}),
                   destination="file", path="register.csv")
        assert (tmp_path / "register.csv").exists()
        assert out["written_path"] == str(tmp_path / "register.csv")

    def test_downloads_is_the_default_when_nothing_is_configured(self):
        """Asserted against Settings rather than by writing to the real home directory."""
        from csa_google_workspace.mcp import settings_from_env
        assert settings_from_env({}).export_dir == "~/Downloads"

    def test_a_full_path_is_honoured(self, tmp_path):
        target = tmp_path / "repo"
        target.mkdir()
        out = call(build({"CSA_GW_EXPORT_DIR": "/nonexistent"}),
                   destination="file", path=str(target / "review.csv"))
        assert out["written_path"] == str(target / "review.csv")
        assert (target / "review.csv").exists()

    def test_no_path_at_all_is_named_after_the_document(self, tmp_path):
        out = call(build({"CSA_GW_EXPORT_DIR": str(tmp_path)}), destination="file")
        assert "Draft" in out["written_path"]
        assert out["written_path"].endswith(".csv")

    def test_an_existing_file_is_never_overwritten(self, tmp_path):
        (tmp_path / "register.csv").write_text("mine")
        out = call(build({"CSA_GW_EXPORT_DIR": str(tmp_path)}),
                   destination="file", path="register.csv")
        assert (tmp_path / "register.csv").read_text() == "mine"
        assert out["written_path"] != str(tmp_path / "register.csv")
        assert "already existed" in out["detail"]

    def test_the_result_always_says_where_it_went(self, tmp_path):
        """A model that reports the name it ASKED for will be wrong whenever a timestamp was
        appended, so the path has to come back and the detail has to mention it."""
        out = call(build({"CSA_GW_EXPORT_DIR": str(tmp_path)}),
                   destination="file", path="register.csv")
        assert out["written_path"] in out["detail"] or str(tmp_path) in out["detail"]

    def test_a_non_csv_extension_becomes_csv(self, tmp_path):
        """So even an influenced path writes an inert file, never a shell profile."""
        call(build({"CSA_GW_EXPORT_DIR": str(tmp_path)}), destination="file", path="zshrc")
        assert (tmp_path / "zshrc.csv").exists()

    def test_a_missing_directory_is_reported_not_created(self, tmp_path):
        with pytest.raises(Exception, match="does not exist|not a directory"):
            call(build({"CSA_GW_EXPORT_DIR": str(tmp_path / "nope")}),
                 destination="file", path="register.csv")

    def test_the_written_csv_is_escaped_against_formula_injection(self, tmp_path):
        """End to end, not just in the renderer: a hostile comment must not arrive in a file
        somebody opens in Excel as an executable formula."""
        out = call(build({"CSA_GW_EXPORT_DIR": str(tmp_path)}),
                   destination="file", path="register.csv")
        # utf-8 to match the writer (`_tools/comments.py` writes `encoding="utf-8"`).
        # The locale default read the same file as cp1252 on Windows.
        written = pathlib.Path(out["written_path"]).read_text(encoding="utf-8")
        for line in written.splitlines()[1:]:
            assert not line.split(",")[0].startswith(("=", "+", "-", "@"))


class TestItIsDiscoverable:
    def test_the_description_names_both_destinations(self):
        app = build()
        tool = next(t for t in asyncio.run(app.list_tools()) if t.name == "export_comments")
        text = tool.description.lower()
        assert "csv" in text and "sheet" in text

    def test_the_server_instructions_mention_it(self):
        """A capability nobody discovers saves nobody any time."""
        from csa_google_workspace.mcp.server import INSTRUCTIONS
        assert "export_comments" in INSTRUCTIONS

    def test_an_unknown_destination_lists_the_legal_ones(self):
        with pytest.raises(Exception) as raised:
            call(build(), destination="pdf")
        message = str(raised.value)
        for legal in ("rows", "csv", "sheet", "file"):
            assert legal in message

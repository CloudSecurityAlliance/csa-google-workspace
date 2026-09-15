"""Where a CSV goes, and what must not be in it.

Two separate concerns that both live on the write path.

**Formula injection.** A comment on a shared document can begin with `=`, `+`, `-` or `@`, and
Excel reads such a cell as a FORMULA when the file is opened - `=cmd|' /C calc'!A0` being the
classic DDE payload. Anyone who can comment on a document we share can plant it, and the entire
purpose of this feature is that a human opens the result in a spreadsheet. v0.24.0 shipped
without the escape; this is the fix. The Google Sheet destination was never affected, because
the Sheets write uses `RAW`, which stores values as text rather than parsing them.

**Where the file lands.** `~/Downloads` is the default because it is the platform's designated
"a program gave me a file" location - discoverable in the Finder sidebar, persistent, and nobody
keeps precious unique files there. But a full path has to be allowed, for two concrete reasons:
a Claude Desktop *project* may only be able to write inside its own folder, where `~/Downloads`
is not reachable; and a Claude Code user wants the register in the repo they are working in.
Confining to Downloads would break exactly the cases where the file is most useful.

What makes an arbitrary path safe is not validating it but making the failure modes inert:

  * **nothing is ever overwritten** - an existing target gets `-TIMESTAMP` appended, so the worst
    case is an unexpected file rather than a destroyed one;
  * **the extension is forced to `.csv`**, so `~/.zshrc` becomes `~/.zshrc.csv` and is inert;
  * **directories are never created**, so a path cannot conjure a tree;
  * **the resolved absolute path is always reported**, because visibility is the last control -
    and if a timestamp was appended, it must SAY so, or the user goes looking for a name that
    does not exist.
"""
from __future__ import annotations

import csv as csvmod
import io

import pytest

from csa_google_workspace import _export


class TestFormulaInjection:
    @pytest.mark.parametrize("payload", [
        "=cmd|' /C calc'!A0", "+1+1", "-2+3", "@SUM(A1)", "\tsneaky", "\rsneaky"])
    def test_a_cell_excel_would_execute_is_neutralised(self, payload):
        out = _export.to_csv(["text"], [{"text": payload}])
        cell = list(csvmod.reader(io.StringIO(out)))[1][0]
        assert not cell.startswith(("=", "+", "-", "@", "\t", "\r"))
        assert payload in cell, "the original text must still be readable, just not executable"

    def test_ordinary_text_is_untouched(self):
        out = _export.to_csv(["text"], [{"text": "Is this accurate?"}])
        assert list(csvmod.reader(io.StringIO(out)))[1][0] == "Is this accurate?"

    def test_a_negative_number_is_still_legible(self):
        """`-2` is escaped, because Excel cannot tell it from a formula either - but the reader
        must still be able to see what the value was."""
        out = _export.to_csv(["n"], [{"n": "-2"}])
        assert "-2" in list(csvmod.reader(io.StringIO(out)))[1][0]

    def test_the_sheets_grid_is_NOT_escaped(self):
        """A Sheets write uses RAW, so the value is stored as text and a leading `=` is inert.
        Escaping there would put a stray apostrophe into somebody's spreadsheet."""
        grid = _export.to_grid(["text"], [{"text": "=A1"}])
        assert grid[1][0] == "=A1"


class TestWhereItLands:
    def test_a_bare_filename_goes_to_the_default_directory(self, tmp_path):
        target, note = _export.resolve_export_path(
            "register", default_dir=str(tmp_path), doc_name="Draft", stamp="20260826-1513")
        assert target.parent == tmp_path.resolve()
        assert target.name == "register.csv"
        assert str(tmp_path) in note, "the user has to be told where it went"

    def test_no_filename_at_all_is_named_after_the_document(self, tmp_path):
        target, _ = _export.resolve_export_path(
            None, default_dir=str(tmp_path), doc_name="AICM Draft", stamp="20260826-1513")
        assert "AICM" in target.name and target.suffix == ".csv"

    def test_a_full_path_is_honoured(self, tmp_path):
        wanted = tmp_path / "repo" / "review.csv"
        wanted.parent.mkdir()
        target, _ = _export.resolve_export_path(
            str(wanted), default_dir="/nonexistent", doc_name="D", stamp="s")
        assert target == wanted.resolve()

    def test_a_tilde_path_is_expanded(self, tmp_path, monkeypatch):
        # BOTH, because `expanduser` reads a different variable per platform: posixpath
        # uses HOME, ntpath uses USERPROFILE and never consults HOME at all. Setting only
        # HOME left `~` resolving to the real profile on Windows, so this test compared a
        # developer's actual home against tmp_path. (#453)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        target, _ = _export.resolve_export_path(
            "~/review.csv", default_dir=str(tmp_path), doc_name="D", stamp="s")
        assert target == (tmp_path / "review.csv").resolve()


class TestNothingIsEverOverwritten:
    def test_an_existing_target_gets_a_timestamp(self, tmp_path):
        (tmp_path / "register.csv").write_text("mine")
        target, note = _export.resolve_export_path(
            "register.csv", default_dir=str(tmp_path), doc_name="D", stamp="20260826-1513")
        assert target.name == "register-20260826-1513.csv"
        assert (tmp_path / "register.csv").read_text() == "mine"

    def test_the_note_says_the_name_changed(self, tmp_path):
        """Otherwise the user looks for the name they asked for and thinks it failed."""
        (tmp_path / "register.csv").write_text("mine")
        _, note = _export.resolve_export_path(
            "register.csv", default_dir=str(tmp_path), doc_name="D", stamp="20260826-1513")
        assert "already" in note.lower() or "existed" in note.lower()
        assert "register-20260826-1513.csv" in note


class TestTheInertFailureModes:
    def test_a_non_csv_extension_becomes_csv(self, tmp_path):
        target, _ = _export.resolve_export_path(
            str(tmp_path / ".zshrc"), default_dir=str(tmp_path), doc_name="D", stamp="s")
        assert target.name == ".zshrc.csv"

    def test_a_missing_directory_is_refused_not_created(self, tmp_path):
        with pytest.raises(ValueError, match="does not exist|not a directory"):
            _export.resolve_export_path(str(tmp_path / "nope" / "x.csv"),
                                        default_dir=str(tmp_path), doc_name="D", stamp="s")

    def test_a_missing_default_directory_is_refused_with_the_remedy(self, tmp_path):
        """`~/Downloads` genuinely may not exist - a fresh container, a locked-down profile -
        and the error has to say what to do rather than just failing."""
        with pytest.raises(ValueError) as raised:
            _export.resolve_export_path("x.csv", default_dir=str(tmp_path / "nope"),
                                        doc_name="D", stamp="s")
        assert "path" in str(raised.value).lower()

    def test_a_document_name_with_separators_cannot_escape(self, tmp_path):
        """The generated name comes from a DOCUMENT TITLE, which is untrusted - somebody can
        name a Doc `../../etc/passwd`."""
        target, _ = _export.resolve_export_path(
            None, default_dir=str(tmp_path), doc_name="../../etc/passwd", stamp="s")
        assert target.parent == tmp_path.resolve()

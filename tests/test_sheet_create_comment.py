import pytest

from csa_google_workspace import Workspace
from csa_google_workspace import exceptions as exc
from csa_google_workspace.backend import FakeBackend

SHEET = "application/vnd.google-apps.spreadsheet"
META = {"s": {"id": "s", "name": "S", "mimeType": SHEET, "webViewLink": "https://x/spreadsheets/d/s/edit"}}


def _sheet(tabs):
    b = FakeBackend(META, spreadsheets={"s": {"sheets": [
        {"properties": {"sheetId": sid, "title": t}} for t, sid in tabs]}},
        values={("s", t if " " not in t else f"'{t}'"): [["a", "b"]] for t, _ in tabs})
    return Workspace(b).open("s")


def test_create_comment_with_cell_embeds_deeplink():
    s = _sheet([("Sheet1", 0)])
    c = s.create_comment("check this", cell="B11")
    assert "gid=0" in c.content and "range=B11" in c.content and "check this" in c.content


def test_create_comment_without_cell_is_plain():
    s = _sheet([("Sheet1", 0)])
    c = s.create_comment("just a note")
    assert c.content == "just a note"


def test_as_text_quotes_tab_with_spaces():
    s = _sheet([("Q1 Budget", 0)])   # values fixture keyed by the quoted range
    # should not raise / should read via the quoted range
    assert s.as_text() == "a\tb"


def test_quote_tab_escapes_embedded_apostrophe():
    s = _sheet([("Sheet1", 0)])
    assert s._quote_tab("O'Brien") == "'O''Brien'"
    assert s._quote_tab("Q1 Budget") == "'Q1 Budget'"
    assert s._quote_tab("Sheet1") == "Sheet1"


def test_quote_tab_quotes_cell_like_names():
    s = _sheet([("Sheet1", 0)])
    assert s._quote_tab("Q1") == "'Q1'"
    assert s._quote_tab("AB12") == "'AB12'"
    assert s._quote_tab("Sheet1") == "Sheet1"


def test_create_comment_read_only_raises_before_any_spreadsheet_network_call():
    # No `spreadsheets` fixture at all: if _gid() (get_spreadsheet) ran before the
    # read_only check, this would raise NotFoundError instead of ReadOnlyError.
    b = FakeBackend(META)
    s = Workspace(b, read_only=True).open("s")
    with pytest.raises(exc.ReadOnlyError):
        s.create_comment("check this", cell="B1")


def test_create_comment_invalidates_cell_map_cache():
    s = _sheet([("Sheet1", 0)])
    s._cell_map_cache = {"stale": "value"}
    s.create_comment("just a note")
    assert s._cell_map_cache is None


def test_create_comment_accepts_content_keyword_matching_base():
    # Audit #10 (LSP): the override must keep the base's `content` parameter name
    # so generic `document.create_comment(content=...)` works for any concrete type.
    s = _sheet([("Sheet1", 0)])
    c = s.create_comment(content="hello")
    assert c.content == "hello"

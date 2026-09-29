"""Which TAB is a spreadsheet comment on — the half of the cell mapping that was missing.

`Location.tab` was declared and never populated (#290), so `B4` on a two-tab workbook named
two different cells and the library could not say which. Recovering it means walking the XLSX
relationship graph, and the shape of that graph is the whole difficulty:

```
xl/workbook.xml             <sheet name="Sheet1" r:id="rId5"/>
xl/_rels/workbook.xml.rels  rId5 -> worksheets/sheet1.xml
xl/worksheets/_rels/sheet1.xml.rels
                            .../threadedComment -> ../threadedComments/threadedComment1.xml
```

Every fixture here uses the shape a **real Google export** has, probed 2026-08-31 rather than
taken from the spec — in particular `rId5`/`rId6` for the first two sheets, because the obvious
shortcut (`threadedComment1.xml` belongs to the first sheet) is wrong on real data.

**What this does NOT do**, asserted below so nobody relies on it: it does not break ties in
`match_locations`. A Drive comment carries no sheet information, so when two XLSX entries tie on
(author, text, second) the tab cannot say which Drive comment is which. Both stay unmapped.
"""
from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime

from csa_google_workspace import _cellmap
from csa_google_workspace.comments import Author, Comment

TC_NS = "http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments"
PKG_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
WB_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
TC_REL = "http://schemas.microsoft.com/office/2017/10/relationships/threadedComment"

PERSONS = f'<personList xmlns="{TC_NS}"><person displayName="Kurt" id="P1"/></personList>'


def _threaded(entries):
    """entries: (ref, dT, id, text)"""
    body = "".join(
        f'<threadedComment ref="{ref}" dT="{dt}" personId="P1" id="{cid}">'
        f"<text>{text}</text></threadedComment>"
        for ref, dt, cid, text in entries)
    return f'<ThreadedComments xmlns="{TC_NS}">{body}</ThreadedComments>'


def _workbook(sheets):
    """sheets: (name, rid). Mirrors Google: rIds start at 5, not 1."""
    inner = "".join(f'<sheet state="visible" name="{n}" sheetId="{i+1}" r:id="{r}"/>'
                    for i, (n, r) in enumerate(sheets))
    return (f'<workbook xmlns="{WB_NS}" xmlns:r="{R_NS}">'
            f"<sheets>{inner}</sheets></workbook>")


def _rels(items):
    """items: (id, type, target)"""
    inner = "".join(f'<Relationship Id="{i}" Type="{t}" Target="{g}"/>' for i, t, g in items)
    return f'<Relationships xmlns="{PKG_NS}">{inner}</Relationships>'


def build(sheets, *, comments_by_part=None, sheet_rels=None, omit=()):
    """A workbook whose relationship graph matches a real Google export.

    `sheets`         -- [(name, rid), ...]
    comments_by_part -- {"xl/threadedComments/threadedCommentN.xml": [entries]}
    sheet_rels       -- {"sheet1.xml": [(id, type, target), ...]} to override/omit links
    omit             -- member paths to leave out entirely
    """
    comments_by_part = comments_by_part or {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        def put(name, data):
            if name not in omit:
                z.writestr(name, data)

        put("xl/persons/person.xml", PERSONS)
        put("xl/workbook.xml", _workbook(sheets))
        put("xl/_rels/workbook.xml.rels", _rels(
            [(rid, f"{R_NS}/worksheet", f"worksheets/sheet{i+1}.xml")
             for i, (_, rid) in enumerate(sheets)]))
        for i, _ in enumerate(sheets):
            base = f"sheet{i+1}.xml"
            if sheet_rels is not None and base in sheet_rels:
                items = sheet_rels[base]
            else:
                part = f"xl/threadedComments/threadedComment{i+1}.xml"
                items = ([(("rId2"), TC_REL, f"../threadedComments/threadedComment{i+1}.xml")]
                         if part in comments_by_part else [])
            put(f"xl/worksheets/_rels/{base}.rels", _rels(items))
        for part, entries in comments_by_part.items():
            put(part, _threaded(entries))
    return buf.getvalue()


def _comment(cid, content, dt):
    return Comment(id=cid, author=Author("Kurt", None, False, None), content=content,
                   html_content=content, quoted_text=None, anchor=None, location=None,
                   resolved=False, deleted=False, created_time=dt, modified_time=dt, replies=[])


T = "2026-08-31T10:00:00"
DT = datetime(2026, 8, 31, 10, 0, 0, tzinfo=UTC)


class TestTheSheetNameIsRecovered:
    def test_a_single_sheet_workbook_names_its_tab(self):
        xlsx = build([("Data", "rId5")], comments_by_part={
            "xl/threadedComments/threadedComment1.xml": [("A3", T, "c1", "hello")]})
        roots = _cellmap.parse_xlsx_comments(xlsx)
        assert [r["sheet"] for r in roots] == ["Data"]

    def test_two_sheets_each_comment_gets_its_own_tab(self):
        """The point of #290. Both comments are at B4; only the tab tells them apart."""
        xlsx = build([("Summary", "rId5"), ("Detail", "rId6")], comments_by_part={
            "xl/threadedComments/threadedComment1.xml": [("B4", T, "c1", "first")],
            "xl/threadedComments/threadedComment2.xml": [("B4", T, "c2", "second")]})
        by_text = {r["text"]: r["sheet"] for r in _cellmap.parse_xlsx_comments(xlsx)}
        assert by_text == {"first": "Summary", "second": "Detail"}

    def test_a_non_sequential_rid_still_resolves(self):
        """Google numbers the first sheet `rId5`. Mapping `threadedComment1.xml` to "the first
        sheet" by position happens to work here and breaks as soon as sheet order and rId order
        diverge - so the graph is walked, and this fixture proves the walk is real."""
        xlsx = build([("Only", "rId9")], comments_by_part={
            "xl/threadedComments/threadedComment1.xml": [("A1", T, "c1", "x")]})
        assert _cellmap.parse_xlsx_comments(xlsx)[0]["sheet"] == "Only"

    def test_a_relative_target_is_normalised(self):
        """`../threadedComments/x.xml` is relative to `xl/worksheets/`. Used unnormalised as a
        zip key it matches nothing, and the tab silently comes back None."""
        xlsx = build([("S", "rId5")], comments_by_part={
            "xl/threadedComments/threadedComment1.xml": [("A1", T, "c1", "x")]},
            sheet_rels={"sheet1.xml": [
                ("rId2", TC_REL, "../threadedComments/threadedComment1.xml")]})
        assert _cellmap.parse_xlsx_comments(xlsx)[0]["sheet"] == "S"

    def test_a_sheet_with_no_comments_is_not_an_error(self):
        """Real exports do this: a sheet with no comments has no threadedComment relationship
        at all, only (say) a drawing. Absence is normal."""
        xlsx = build([("Has", "rId5"), ("HasNot", "rId6")], comments_by_part={
            "xl/threadedComments/threadedComment1.xml": [("A1", T, "c1", "x")]},
            sheet_rels={"sheet2.xml": [("rId1", f"{R_NS}/drawing", "../drawings/d2.xml")]})
        roots = _cellmap.parse_xlsx_comments(xlsx)
        assert len(roots) == 1 and roots[0]["sheet"] == "Has"


class TestTheTabReachesTheLocation:
    def test_a_matched_comment_carries_its_tab(self):
        xlsx = build([("Ledger", "rId5")], comments_by_part={
            "xl/threadedComments/threadedComment1.xml": [("C7", T, "c1", "check this")]})
        roots = _cellmap.parse_xlsx_comments(xlsx)
        got = _cellmap.match_locations([_comment("X1", "check this", DT)], roots)
        loc = got["X1"]
        assert (loc.cell, loc.row, loc.col, loc.tab) == ("C7", 7, 3, "Ledger")

    def test_location_from_ref_takes_an_explicit_tab(self):
        assert _cellmap.location_from_ref("B11", tab="Sheet2").tab == "Sheet2"

    def test_location_from_ref_defaults_to_no_tab(self):
        """A caller that does not know the tab must not have one invented for it."""
        assert _cellmap.location_from_ref("B11").tab is None


class TestWhenTheGraphCannotBeWalked:
    """The tab degrades to None. The CELL must survive - it is the more valuable half, and it
    does not depend on the relationship graph at all."""

    def test_a_missing_workbook_still_yields_cells(self):
        xlsx = build([("S", "rId5")], comments_by_part={
            "xl/threadedComments/threadedComment1.xml": [("D9", T, "c1", "x")]},
            omit=("xl/workbook.xml",))
        roots = _cellmap.parse_xlsx_comments(xlsx)
        assert roots[0]["ref"] == "D9" and roots[0]["sheet"] is None

    def test_missing_workbook_rels_yields_cells(self):
        xlsx = build([("S", "rId5")], comments_by_part={
            "xl/threadedComments/threadedComment1.xml": [("D9", T, "c1", "x")]},
            omit=("xl/_rels/workbook.xml.rels",))
        assert _cellmap.parse_xlsx_comments(xlsx)[0]["sheet"] is None

    def test_missing_sheet_rels_yields_cells(self):
        xlsx = build([("S", "rId5")], comments_by_part={
            "xl/threadedComments/threadedComment1.xml": [("D9", T, "c1", "x")]},
            omit=("xl/worksheets/_rels/sheet1.xml.rels",))
        assert _cellmap.parse_xlsx_comments(xlsx)[0]["sheet"] is None

    def test_malformed_workbook_xml_does_not_raise(self):
        """Never fail an export over a tab name."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("xl/persons/person.xml", PERSONS)
            z.writestr("xl/workbook.xml", "<not xml at all")
            z.writestr("xl/threadedComments/threadedComment1.xml",
                       _threaded([("A1", T, "c1", "x")]))
        roots = _cellmap.parse_xlsx_comments(buf.getvalue())
        assert len(roots) == 1 and roots[0]["sheet"] is None

    def test_an_unresolved_tab_is_none_not_a_guess(self):
        """`tab=None` on a Location means "the cell is known, the sheet is not". It must never
        be filled with the first sheet's name as a plausible default - that is the `list_labels`
        mistake: a confident wrong answer where an absence was the truth."""
        xlsx = build([("First", "rId5"), ("Second", "rId6")], comments_by_part={
            "xl/threadedComments/threadedComment1.xml": [("A1", T, "c1", "x")]},
            omit=("xl/worksheets/_rels/sheet1.xml.rels",))
        got = _cellmap.match_locations([_comment("X1", "x", DT)], xlsx and
                                       _cellmap.parse_xlsx_comments(xlsx))
        assert got["X1"].tab is None
        assert got["X1"].cell == "A1", "the cell is independent of the graph and must survive"


class TestTheTabDoesNotBreakTies:
    def test_duplicates_on_different_tabs_still_yield_no_match(self):
        """Asserted so the reasoning is recorded, because it looks like it should help. A DRIVE
        comment carries no sheet, so knowing one XLSX entry is on Summary and the other on
        Detail does not say which Drive comment is which. Dropping both stays correct."""
        xlsx = build([("Summary", "rId5"), ("Detail", "rId6")], comments_by_part={
            "xl/threadedComments/threadedComment1.xml": [("B4", T, "c1", "same text")],
            "xl/threadedComments/threadedComment2.xml": [("B4", T, "c2", "same text")]})
        roots = _cellmap.parse_xlsx_comments(xlsx)
        assert len({r["sheet"] for r in roots}) == 2, "precondition: they differ only by tab"
        assert _cellmap.match_locations([_comment("X1", "same text", DT)], roots) == {}

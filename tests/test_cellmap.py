import io, zipfile
from datetime import datetime, timezone
from csa_google_workspace import _cellmap
from csa_google_workspace.comments import Comment, Author, Location

NS = "http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments"


def _xlsx(threaded_xml, persons_xml):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/threadedComments/threadedComment1.xml", threaded_xml)
        z.writestr("xl/persons/person.xml", persons_xml)
    return buf.getvalue()

PERSONS = f'<personList xmlns="{NS}"><person displayName="Kurt" id="P1"/></personList>'


def _threaded(entries):  # entries: list of (ref, dT, id, text, parentId|None)
    body = ""
    for ref, dT, cid, text, parent in entries:
        p = f' parentId="{parent}"' if parent else ""
        body += (f'<threadedComment ref="{ref}" dT="{dT}" personId="P1" id="{cid}"{p}>'
                 f'<text>{text}</text></threadedComment>')
    return f'<ThreadedComments xmlns="{NS}">{body}</ThreadedComments>'


def _comment(cid, content, dt):
    return Comment(id=cid, author=Author("Kurt", None, False, None), content=content,
                   html_content=content, quoted_text=None, anchor=None, location=None,
                   resolved=False, deleted=False, created_time=dt, modified_time=dt, replies=[])


def test_location_from_ref_computes_row_col():
    loc = _cellmap.location_from_ref("B11")
    assert (loc.cell, loc.row, loc.col) == ("B11", 11, 2)


def test_parse_extracts_roots_and_skips_replies():
    xml = _threaded([("B11", "2026-07-20T23:05:59.00", "R1", "hi there", None),
                     ("B11", "2026-07-20T23:06:00.00", "R2", "a reply", "R1")])
    roots = _cellmap.parse_xlsx_comments(_xlsx(xml, PERSONS))
    assert len(roots) == 1
    assert roots[0]["ref"] == "B11" and roots[0]["author"] == "Kurt" and roots[0]["text"] == "hi there"


def test_match_by_author_content_second():
    xml = _threaded([("B11", "2026-07-20T23:05:59.00", "R1", "hi there", None)])
    roots = _cellmap.parse_xlsx_comments(_xlsx(xml, PERSONS))
    c = _comment("cid1", "hi there", datetime(2026, 7, 20, 23, 5, 59, 479000, tzinfo=timezone.utc))
    out = _cellmap.match_locations([c], roots)
    assert out["cid1"].cell == "B11"


def test_ambiguous_duplicate_yields_no_match():
    xml = _threaded([("B11", "2026-07-20T23:05:59.00", "R1", "dup", None),
                     ("C22", "2026-07-20T23:05:59.00", "R2", "dup", None)])
    roots = _cellmap.parse_xlsx_comments(_xlsx(xml, PERSONS))
    c = _comment("cid1", "dup", datetime(2026, 7, 20, 23, 5, 59, tzinfo=timezone.utc))
    assert _cellmap.match_locations([c], roots) == {}   # ambiguous -> no guess

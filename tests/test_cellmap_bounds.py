"""Defense-in-depth bounds on the XLSX comment parse path (audit SEC-1 / #42).

A crafted/oversized export must not be able to OOM the process: per-member size, total
uncompressed budget, and member count are all capped. `ZipInfo.file_size` comes from the
archive header, so an oversized member is rejected before it is decompressed.
"""
import io
import zipfile

from csa_google_workspace import _cellmap

NS = "http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments"


def _zip(members: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:   # ZIP_STORED -> file_size == len(data)
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


def _tc(ref: str, text: str) -> bytes:
    return (f'<ThreadedComments xmlns="{NS}"><threadedComment ref="{ref}" '
            f'dT="2026-01-01T00:00:00" personId="P1"><text>{text}</text></threadedComment>'
            f'</ThreadedComments>').encode()


def test_normal_member_parses_within_default_caps():
    roots = _cellmap.parse_xlsx_comments(
        _zip({"xl/threadedComments/threadedComment1.xml": _tc("B2", "hi")}))
    assert [r["ref"] for r in roots] == ["B2"]


def test_oversized_member_is_skipped_not_parsed(monkeypatch, caplog):
    monkeypatch.setattr(_cellmap, "_MAX_MEMBER_UNCOMPRESSED", 50)   # 50 bytes
    data = _zip({"xl/threadedComments/threadedComment1.xml": _tc("A1", "x" * 500)})
    import logging
    with caplog.at_level(logging.WARNING, logger="csa_google_workspace._cellmap"):
        roots = _cellmap.parse_xlsx_comments(data)
    assert roots == []                                             # skipped, never decompressed
    assert any("size budget" in r.getMessage() for r in caplog.records)


def test_total_uncompressed_budget_stops_reading(monkeypatch):
    m1, m2 = _tc("A1", "a"), _tc("B2", "b")
    monkeypatch.setattr(_cellmap, "_MAX_TOTAL_UNCOMPRESSED", len(m1))   # room for m1 only
    roots = _cellmap.parse_xlsx_comments(_zip({
        "xl/threadedComments/threadedComment1.xml": m1,
        "xl/threadedComments/threadedComment2.xml": m2,
    }))
    assert [r["ref"] for r in roots] == ["A1"]


def test_member_count_cap(monkeypatch):
    monkeypatch.setattr(_cellmap, "_MAX_MEMBERS", 1)
    roots = _cellmap.parse_xlsx_comments(_zip({
        "xl/threadedComments/threadedComment1.xml": _tc("A1", "a"),
        "xl/threadedComments/threadedComment2.xml": _tc("B2", "b"),
    }))
    assert len(roots) == 1                                         # only the first member read

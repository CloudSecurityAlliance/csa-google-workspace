"""Cross-type end-to-end integration tests against REAL Google.

For each of Doc / Sheet / Slides: create a throwaway file, seed content, drive the
whole library stack (open -> verify type -> read content -> full comment lifecycle),
and trash the file. Supersedes the earlier Doc-only comment/content live tests.

Gated: skipped unless CSA_GW_INTEGRATION=1. Also needs CSA_GW_CLIENT_SECRETS pointing
at an OAuth client-secrets JSON (a cached token avoids re-consent). Nothing here runs
at import/collection time.

    CSA_GW_INTEGRATION=1 CSA_GW_CLIENT_SECRETS=path/to/client_secret.json \
        pytest tests/integration/test_all_types_live.py -v
"""
import contextlib
import datetime
import os

import pytest

from csa_google_workspace import exceptions

pytestmark = pytest.mark.skipif(
    os.environ.get("CSA_GW_INTEGRATION") != "1",
    reason="set CSA_GW_INTEGRATION=1 (and CSA_GW_CLIENT_SECRETS) to run live Google tests",
)


def _ws():
    secrets = os.environ.get("CSA_GW_CLIENT_SECRETS")
    if not secrets:
        pytest.skip("set CSA_GW_CLIENT_SECRETS to the OAuth client-secrets JSON path")
    from csa_google_workspace import Workspace
    return Workspace.from_oauth(secrets)


# Where the throwaway files go. Loose in My Drive root is what this used to do, and it is
# the wrong answer for something that runs unattended every night: the debris is unauditable
# and indistinguishable from a person's own files.
#
#   CSA_GW_TEST_FOLDER   a folder id or URL — used as-is, and NEVER trashed. This is the
#                        setting for a rig with a standing, human-visible scratch folder.
#   unset                `csa-google-workspace-YYYYMMDDHHMM` in My Drive, created fresh per
#                        run and trashed at the end. The name is checked first and never
#                        reused — see `_free_folder_name`.
#
# A folder cannot be trashed with children still in it and have them go too — Drive leaves
# them loose in My Drive (`FileCollection.trash` says so). That works out here because each
# `_throwaway` trashes its own file on exit, so the folder is empty by the time we remove it.
_FOLDER: dict = {"id": None, "ours": False}


def _folder(ws):
    """The folder new files are created in, resolved once per session."""
    if _FOLDER["id"] is not None:
        return _FOLDER["id"]
    configured = os.environ.get("CSA_GW_TEST_FOLDER")
    if configured:
        from csa_google_workspace.workspace import parse_file_id
        _FOLDER["id"] = parse_file_id(configured)
        _FOLDER["ours"] = False
    else:
        ref = ws.files.create(_free_folder_name(ws), "folder")
        _FOLDER["id"], _FOLDER["ours"] = ref.id, True
    return _FOLDER["id"]


def _free_folder_name(ws, _now=None):
    """`csa-google-workspace-YYYYMMDDHHMM`, with a suffix if that name is already taken.

    **Drive does not enforce unique names**, so creating a folder never overwrites one — it
    quietly makes a SECOND folder with the same name. That is the reason to look first, and
    the reason looking is not about overwriting: the hazard is adopting a folder somebody else
    made and filling it with test files, or ending up with two identically-named folders and no
    way to tell which run owned which.

    So a name that is taken is never reused. The timestamp is minute-resolution, which is
    plenty for a nightly rig and short enough to read, and two runs inside the same minute get
    `-2`, `-3` and so on.

    The search sees shared folders too. Skipping a name because somebody else's folder has it
    is the conservative direction and costs nothing but a suffix.
    """
    now = _now or datetime.datetime.now(datetime.UTC)
    base = f"csa-google-workspace-{now.strftime('%Y%m%d%H%M')}"
    name, n = base, 1
    while _folder_named(ws, name):
        n += 1
        name = f"{base}-{n}"
        if n > 50:                       # a loop this long means something else is wrong
            raise RuntimeError(f"50 folders already named like {base!r}; refusing to add another")
    return name


def _folder_named(ws, name):
    """Is there a visible, untrashed folder with exactly this name?"""
    escaped = name.replace("\\", "\\\\").replace("'", "\\'")
    hits = ws.files.search(
        f"name = '{escaped}' and mimeType = 'application/vnd.google-apps.folder'", limit=1)
    return bool(hits)


def cleanup_folder(ws=None):
    """Trash the per-run folder, if this session created it. Called from conftest."""
    if _FOLDER["ours"] and _FOLDER["id"] and ws is not None:
        try:
            ws.files.trash(_FOLDER["id"])
        except Exception:                       # noqa: BLE001 - teardown must not mask a failure
            pass
    _FOLDER["id"], _FOLDER["ours"] = None, False


@contextlib.contextmanager
def _throwaway(ws, kind, name):
    """Create a throwaway Drive file of `kind`; always trash it on exit.

    **Through the PUBLIC API, deliberately (#433).** This helper used to reach
    `ws._backend._services.drive`, and stopped working the day `Workspace` began wrapping its
    backend in `PolicyBackend` unconditionally — that wrapper refuses every `_`-prefixed name,
    which is the fail-closed behaviour #82 built on purpose. The whole suite errored at setup,
    and because it is opt-in nobody noticed for releases; the P0 fixed in v0.51.1 shipped five
    times underneath it.

    So the rule now: **a live suite drives the same surface a caller drives.** It is testing
    what people actually use, and it can no longer step around the policy layer it runs under —
    which a suite that exists to catch live-only defects should never have been able to do.
    """
    ref = ws.files.create(name, kind, parent_id=_folder(ws))
    try:
        yield ref.id
    finally:
        ws.files.trash(ref.id)


def _assert_comment_lifecycle(doc):
    """The uniform comment lifecycle — must behave identically on every file type."""
    c = doc.create_comment("please review")
    assert c.resolved is False and c.content == "please review"
    c.reply("ack")
    c.resolve()
    assert doc.comments.get(c.id).resolved is True
    assert doc.comments.filter(resolved=False) == []
    c.reopen()
    assert doc.comments.get(c.id).resolved is False
    c.delete()
    assert doc.comments.all() == []                       # soft-deleted: hidden by default
    assert len(doc.comments.all(include_deleted=True)) == 1


def test_doc_end_to_end_live():
    from csa_google_workspace import Doc
    ws = _ws()
    with _throwaway(ws, "document", "E2E-Doc-THROWAWAY") as fid:
        d = ws.open(fid)
        d.insert_text("E2E doc line one.\n", at=1)
        d = ws.open(fid)
        assert isinstance(d, Doc) and d.type == "document"
        assert "E2E doc line one." in d.as_text()
        assert any("E2E doc line one." in p for p in d.paragraphs)
        assert d.export("application/pdf")[:4] == b"%PDF"
        _assert_comment_lifecycle(d)


def test_sheet_end_to_end_live():
    from csa_google_workspace import Sheet
    ws = _ws()
    with _throwaway(ws, "spreadsheet", "E2E-Sheet-THROWAWAY") as fid:
        s = ws.open(fid)
        s.update("Sheet1!A1", [["Name", "Score"], ["Alice", "10"]])
        assert isinstance(s, Sheet) and s.type == "spreadsheet"
        assert "Sheet1" in s.tabs
        assert s.values("Sheet1!A1:B2") == [["Name", "Score"], ["Alice", "10"]]
        assert "Name\tScore" in s.as_text()
        # multi-tab as_text (Tier 3): a second tab must not be silently dropped
        s.add_tab("Data")
        s.update("Data!A1", [["extra"]])
        full = s.as_text()
        assert "# Sheet1" in full and "# Data" in full and "extra" in full
        assert s.as_text(tab="Data") == "extra"
        _assert_comment_lifecycle(s)


def test_slides_end_to_end_live():
    from csa_google_workspace import Slides
    ws = _ws()
    with _throwaway(ws, "presentation", "E2E-Slides-THROWAWAY") as fid:
        p = ws.open(fid)
        assert isinstance(p, Slides) and p.type == "presentation"
        assert len(p.slides) >= 1
        # `Slide.object_id` is the PAGE id, which every create* request needs. Added with
        # #433: without it the public batch_update cannot target a slide at all, and that
        # gap is part of why this suite was reaching around the public API.
        first = p.slides[0].object_id
        assert first, "a slide must expose its own objectId"
        p.batch_update([
            {"createShape": {"objectId": "e2etextbox1", "shapeType": "TEXT_BOX",
                "elementProperties": {"pageObjectId": first,
                    "size": {"width": {"magnitude": 300, "unit": "PT"},
                             "height": {"magnitude": 50, "unit": "PT"}},
                    "transform": {"scaleX": 1, "scaleY": 1,
                                  "translateX": 50, "translateY": 50, "unit": "PT"}}}},
            {"insertText": {"objectId": "e2etextbox1", "text": "E2E slide text"}}])
        assert "E2E slide text" in ws.open(fid).as_text()
        # Tier 3: the shape objectId is discoverable and insert_text prepends into it
        p2 = ws.open(fid)
        assert "e2etextbox1" in [oid for sl in p2.slides for oid in sl.shape_ids]
        p2.insert_text("e2etextbox1", "PREFIX: ", index=0)
        assert "PREFIX: E2E slide text" in ws.open(fid).as_text()
        _assert_comment_lifecycle(p)


def test_sheet_cell_mapping_live():
    from csa_google_workspace import Sheet
    ws = _ws()
    with _throwaway(ws, "spreadsheet", "E2E-CellMap-THROWAWAY") as fid:
        s = ws.open(fid)
        s.update("A1", [["hdr"]])
        assert isinstance(s, Sheet)
        c = s.create_comment("map me")           # API comment -> lands on A1 in the export
        loc = s.comments.get(c.id).location
        assert loc is not None and loc.cell == "A1", f"expected A1, got {loc}"
        c.delete()


def test_content_write_live():
    ws = _ws()
    with _throwaway(ws, "document", "E2E-DocWrite-THROWAWAY") as fid:
        d = ws.open(fid)
        # SEED FIRST. "Appended text is not at the start" is vacuous on an EMPTY document,
        # where the only content is what you just appended — the assertion below then fails
        # for a reason that has nothing to do with #391. It had never run: every test in this
        # file errored at setup (#433), so this guard was written and never once executed.
        d.insert_text("FIRST LINE, seeded so position means something.\n", at=1)
        d = ws.open(fid)
        # A leading marker, so POSITION is checked and not merely presence. The old assertion
        # was `"..." in as_text()`, which is true whether the text lands at the end or the
        # start - and #391 landed it at the start on every call for as long as
        # `includeTabsContent` has been set. A containment check cannot see position, which is
        # why this suite was green against live Google while the bug was real.
        d.append_text("\nHEAD-MARKER written by the library")
        text = ws.open(fid).as_text()
        assert "HEAD-MARKER written by the library" in text
        assert not text.lstrip().startswith("HEAD-MARKER"), (
            "append_text wrote to the START of the document (#391)")
        assert text.rstrip().endswith("HEAD-MARKER written by the library"), (
            "appended text must be at the end")
        d.replace_text("HEAD-MARKER written by the library",
                       "edited by the library")
        assert "edited by the library" in ws.open(fid).as_text()
    with _throwaway(ws, "spreadsheet", "E2E-SheetWrite-THROWAWAY") as sid:
        s = ws.open(sid)
        s.update("Sheet1!A1", [["hello", "world"]])
        assert s.values("Sheet1!A1:B1") == [["hello", "world"]]
        s.append_rows("Sheet1!A1", [["r2a", "r2b"]])          # Tier 3: values.append INSERT_ROWS
        assert s.values("Sheet1!A2:B2") == [["r2a", "r2b"]]
        s.clear("Sheet1!A1:B2")
        assert s.values("Sheet1!A1:B2") == []


def test_suggestions_read_live():
    doc_id = os.environ.get("CSA_GW_SUGGESTIONS_DOC")
    if not doc_id:
        pytest.skip("set CSA_GW_SUGGESTIONS_DOC to a Doc id that has suggesting-mode edits")
    from csa_google_workspace import Doc
    ws = _ws()
    d = ws.open(doc_id)
    assert isinstance(d, Doc)
    sugg = d.suggestions
    assert isinstance(sugg, list) and all(s.kind in ("insertion", "deletion") for s in sugg)
    # accepted vs rejected previews should differ when suggestions exist
    if sugg:
        assert d.as_text(suggestions="accepted") != d.as_text(suggestions="rejected")


def test_markdown_export_keeps_structure_live():
    """The claim that makes format breadth worth building: Drive's Markdown conversion
    preserves structure, unlike as_text() (text runs only). Verified, not assumed —
    a heading must come back as `# `, not as bare text."""
    ws = _ws()
    with _throwaway(ws, "document", "csa-gw markdown export") as fid:
        doc = ws.open(fid)
        doc.batch_update([
            {"insertText": {"location": {"index": 1}, "text": "Findings\nA bullet\n"}},
            {"updateParagraphStyle": {
                "range": {"startIndex": 1, "endIndex": 9},
                "paragraphStyle": {"namedStyleType": "HEADING_1"},
                "fields": "namedStyleType"}},
            {"createParagraphBullets": {
                "range": {"startIndex": 10, "endIndex": 18},
                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"}},
        ])

        md = doc.as_markdown()
        assert "# Findings" in md, md
        assert "A bullet" in md and md.count("*") + md.count("-") > 0, md

        # as_text() sees the same words with none of the structure — the contrast that
        # justifies a separate accessor.
        assert "# Findings" not in doc.as_text()

        assert "text/markdown" in doc.export_formats
        with pytest.raises(exceptions.UnsupportedOperation):
            ws.open(fid).export("pptx")            # wrong type for a Doc, refused locally


def test_search_and_recent_live():
    """Discovery against a real Drive. Asserts the query reaches Google correctly and that
    the shared-drive flags do not break an ordinary personal-drive search."""
    ws = _ws()
    marker = "csa-gw-search-probe"
    with _throwaway(ws, "document", f"{marker} doc") as fid:
        hits = ws.files.search(f"name contains '{marker}'")
        assert [h.id for h in hits] == [fid], [repr(h) for h in hits]
        hit = hits[0]
        assert hit.type == "document" and hit.openable
        assert hit.modified_time is not None
        assert hit.open().id == fid                       # upgrade to a typed Document

        assert fid in [h.id for h in ws.files.recent(limit=25)]
        assert marker not in repr(hit)                    # the redacted repr, live


def test_permissions_read_live():
    """A freshly created file has exactly one permission — its owner, us. Anything else
    means the fields/supportsAllDrives wiring is wrong."""
    ws = _ws()
    with _throwaway(ws, "document", "csa-gw perms probe") as fid:
        perms = ws.open(fid).permissions
        assert len(perms) == 1, [repr(p) for p in perms]
        owner = perms[0]
        assert owner.role == "owner" and owner.type == "user"
        assert owner.can_write and not owner.is_public
        assert owner.email and "@" in owner.email      # the field Drive omits by default
        assert owner.email not in repr(owner)          # redacted repr, live

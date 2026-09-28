"""The register's remaining refusals, and the notes that make a re-run readable.

Three groups, and they fail in three different ways when they are wrong:

**The archive guard.** A register can arrive as `.xlsx`, which is a zip, which means a zip
bomb - and this parses a file somebody was handed. The guard is a cheap header check, not a
complete defence, and the important property is that it refuses rather than that it is
thorough.

**"Already done" is not "nothing happened".** A delete register run twice is the most ordinary
flow this feature has. Every row has to say which of the three it was - done now, done before,
or not applicable - because the report is what somebody reads instead of opening Drive.

**`force` is scoped, and says where it stops.** It overrides the reply marker, because
re-posting the same text is a coherent thing to want. It invents nothing for delete or
resolve, and #169 is what happens when that silence is left implicit: a row saying "already
marked done" is indistinguishable from force having been honoured and found nothing to do.
"""
from __future__ import annotations

import csv
import zipfile

import pytest

from csa_google_workspace import _apply


class TestTheArchiveGuard:
    """`.xlsx` is a zip, and this one was handed over by somebody."""

    @staticmethod
    def zip_with(path, members):
        with zipfile.ZipFile(path, "w") as archive:
            for name, body in members:
                archive.writestr(name, body)
        return path

    def test_too_many_members_is_refused_by_count(self, tmp_path):
        """A zip bomb does not need to be large on disk. Counting members costs nothing and
        catches the shape where thousands of tiny entries each expand."""
        path = self.zip_with(tmp_path / "bomb.xlsx",
                             [(f"m{i}.xml", "x") for i in range(_apply.MAX_REGISTER_MEMBERS + 1)])

        with pytest.raises(ValueError, match="archive members"):
            _apply._check_archive_bounds(path)

    def test_the_refusal_names_the_limit_and_the_count(self, tmp_path):
        """So a legitimate register that trips it can be told apart from an attack, by
        somebody who has to decide which it was."""
        path = self.zip_with(tmp_path / "bomb.xlsx",
                             [(f"m{i}.xml", "x") for i in range(_apply.MAX_REGISTER_MEMBERS + 1)])

        with pytest.raises(ValueError) as ei:
            _apply._check_archive_bounds(path)
        assert str(_apply.MAX_REGISTER_MEMBERS) in str(ei.value)
        assert str(_apply.MAX_REGISTER_MEMBERS + 1) in str(ei.value)

    def test_an_ordinary_register_passes(self, tmp_path):
        assert _apply._check_archive_bounds(
            self.zip_with(tmp_path / "ok.xlsx", [("xl/workbook.xml", "<x/>")])) is None

    @pytest.mark.parametrize("body", [b"not a zip at all", b""])
    def test_a_file_that_is_not_a_zip_is_left_for_openpyxl_to_report(self, tmp_path, body):
        """Deliberately NOT this function's error to raise. openpyxl's message names the file
        and the format; a bounds checker saying "bad zip" would replace a diagnosis with a
        symptom, and the file may not have been meant as .xlsx at all."""
        path = tmp_path / "actually.csv"
        path.write_bytes(body)
        assert _apply._check_archive_bounds(path) is None

    def test_a_missing_file_is_also_left_alone(self, tmp_path):
        assert _apply._check_archive_bounds(tmp_path / "absent.xlsx") is None


class TestFindingAReply:
    """`_find_reply` returns the object off the thread, never a rebuilt one - a hand-built
    reply carries no backend and `.delete()` on it raises `DetachedError`."""

    class FakeReply:
        def __init__(self, reply_id):
            self.id = reply_id

    class FakeThread:
        def __init__(self, replies):
            self.replies = replies

    def test_it_returns_the_object_from_the_thread(self):
        wanted = self.FakeReply("r2")
        thread = self.FakeThread([self.FakeReply("r1"), wanted])
        assert _apply._find_reply(thread, "r2") is wanted

    def test_an_absent_reply_is_none_rather_than_an_invention(self):
        """The caller turns None into "either the register came from a different document, or
        the reply is already gone" - two possibilities it genuinely cannot distinguish. A
        fabricated reply object would turn that into a `DetachedError` three frames away."""
        assert _apply._find_reply(self.FakeThread([self.FakeReply("r1")]), "r2") is None

    def test_a_thread_with_no_replies_at_all_is_none(self):
        assert _apply._find_reply(self.FakeThread([]), "r1") is None

    def test_a_missing_thread_is_none_rather_than_an_attribute_error(self):
        """`by_id.get(parent_id)` returns None when the register names a thread this file does
        not have, and that lands here before anything has checked it."""
        assert _apply._find_reply(None, "r1") is None


class TestTheColumnOrder:
    """The sheet's own order, extended with whatever has to be written back."""

    def test_an_empty_register_still_has_every_column(self):
        """Nothing to take an order FROM. Falling back to the canonical list is what lets an
        empty register be written back at all - the alternative is a header of nothing."""
        columns = _apply.header_for([])
        for name in (*_apply.ACTIONS, *_apply.COMPLETED):
            assert name in columns

    def test_the_sheets_own_order_is_preserved(self):
        """Somebody arranged those columns. Re-ordering them on write-back would make the
        diff between an exported register and an applied one unreadable."""
        given = {"thread_id": "", "my_own_note": "", "content": ""}
        assert _apply.header_for([given])[:3] == ["thread_id", "my_own_note", "content"]

    def test_the_write_back_columns_are_appended_not_inserted(self):
        """At the end, so the columns somebody reads stay where they were."""
        columns = _apply.header_for([{"thread_id": "", "content": ""}])
        assert columns[:2] == ["thread_id", "content"]
        assert set(columns[2:]) >= set(_apply.COMPLETED)


# --- the register applied to a real (fake) document -------------------------------------
#
# Written by hand rather than exported, because every case below needs a row in a state an
# export never produces: a completion marker already set, a reply that is already a tombstone,
# a thread id that does not exist. Exporting and then editing would hide which field is the
# one under test.

import asyncio  # noqa: E402 - the helpers below are a second section, not a second import block

from csa_google_workspace import Workspace  # noqa: E402
from csa_google_workspace.backend import FakeBackend  # noqa: E402
from csa_google_workspace.mcp import settings_from_env  # noqa: E402
from csa_google_workspace.mcp.server import create_server  # noqa: E402
from csa_google_workspace.policy import PolicyBackend  # noqa: E402

DOC = "d1"
DOC_MIME = "application/vnd.google-apps.document"


def thread(thread_id, *, resolved=False, deleted=False, replies=()):
    return {"id": thread_id, "content": f"Point {thread_id}",
            "author": {"displayName": "A"}, "createdTime": "2026-08-20T10:00:00Z",
            "resolved": resolved, "deleted": deleted, "replies": list(replies)}


def reply(reply_id, *, deleted=False):
    return {"id": reply_id, "content": "a reply", "author": {"displayName": "B"},
            "createdTime": "2026-08-20T11:00:00Z", "deleted": deleted}


def server(threads):
    backend = FakeBackend({DOC: {"id": DOC, "name": "Draft", "mimeType": DOC_MIME}},
                          documents={DOC: {"body": {"content": []}}},
                          comments={DOC: threads})
    st = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
                            "CSA_GW_PROFILE": "full"})
    return create_server(lambda: Workspace(PolicyBackend(backend, st.policy)), settings=st)


def write_register(path, rows):
    """A register with the canonical header and only the named fields filled in."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(_apply.COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in _apply.COLUMNS})
    return str(path)


def apply_register(app, path, *, apply=True, force=False):
    return asyncio.run(app.call_tool("apply_comment_actions", {
        "fileId": DOC, "path": path, "apply": apply, "force": force})).structured_content


def details(out):
    return " | ".join(row["detail"] for row in out["rows"])


class TestAlreadyDoneIsSaidOutLoud:
    """Three states, not two: done now, done before, not applicable. The report is what
    somebody reads INSTEAD of opening Drive, so "already done" has to be distinguishable from
    both "done" and "nothing requested"."""

    def test_a_delete_marker_already_set_is_reported_not_repeated(self, tmp_path):
        app = server([thread("t1")])
        path = write_register(tmp_path / "r.csv", [
            {"thread_id": "t1", "delete_comment": "TRUE", "delete_comment_completed": "yes"}])

        out = apply_register(app, path)
        assert "delete already marked done" in details(out)
        assert out["deleted"] == 0, "the marker is trusted; the delete is not re-issued"

    def test_force_says_where_it_stops_for_delete(self, tmp_path):
        """#169's lesson. `force` overrides the REPLY marker, because re-posting the same text
        is coherent. There is no such thing as re-deleting a deleted comment, so instead of
        looking satisfied and doing nothing, the row says force does not apply here."""
        app = server([thread("t1")])
        path = write_register(tmp_path / "r.csv", [
            {"thread_id": "t1", "delete_comment": "TRUE", "delete_comment_completed": "yes"}])

        assert "force does not apply" in details(apply_register(app, path, force=True))

    def test_a_thread_drive_already_shows_as_deleted_is_marked_without_a_call(self, tmp_path):
        """The tombstone. Drive keeps a deleted comment as a stripped shell, so "already
        deleted" is a fact this can READ rather than infer from a failure."""
        app = server([thread("t1", deleted=True)])
        path = write_register(tmp_path / "r.csv", [
            {"thread_id": "t1", "delete_comment": "TRUE"}])

        out = apply_register(app, path)
        assert "already deleted" in details(out)
        assert out["failed"] == 0

    def test_a_resolve_marker_already_set_says_force_has_no_meaning_here(self, tmp_path):
        """Silence was the actual complaint in #169: "already marked done" alone is
        indistinguishable from force having been honoured and found nothing to do. Resolve is
        idempotent and the thread's own `resolved` state is the authority, so there is nothing
        for force to mean - which is now said rather than implied."""
        app = server([thread("t1")])
        path = write_register(tmp_path / "r.csv", [
            {"thread_id": "t1", "resolve_comment": "TRUE", "resolve_comment_completed": "yes"}])

        out = apply_register(app, path, force=True)
        assert "resolve already marked done" in details(out)
        assert "the thread's own resolved state is the authority" in details(out)


class TestADryRunSaysWhatItWould:
    def test_reopening_is_reported_as_would_reopen(self, tmp_path):
        """`apply=false` is the mode somebody runs first. A reopen that reported nothing would
        make the dry run look like "no change requested" - which is the one answer that would
        stop them running it for real."""
        app = server([thread("t1", resolved=True)])
        path = write_register(tmp_path / "r.csv", [
            {"thread_id": "t1", "resolve_comment": "FALSE"}])

        out = apply_register(app, path, apply=False)
        assert "would reopen" in details(out)

        # Counted under `would_reopen`, and `reopened` stays ZERO. The two keys are separate
        # for exactly this reason: a dry run that reported work under the same key as a real
        # one would tell a caller totalling them up that something had already happened.
        assert out["would_reopen"] == 1
        assert out["reopened"] == 0


class TestARowNamingSomethingThatIsNotThere:
    def test_a_reply_id_the_thread_does_not_carry_names_both_possibilities(self, tmp_path):
        """It genuinely cannot tell them apart: the register may have come from a different
        document, or the reply may already be gone. Naming one would be a guess, and the
        remedies are opposite - re-export, versus do nothing."""
        app = server([thread("t1", replies=[reply("r1")])])
        path = write_register(tmp_path / "r.csv", [
            {"thread_id": "r-missing", "reply_to": "t1", "delete_comment": "TRUE"}])

        out = apply_register(app, path)
        detail = details(out)
        assert "no reply" in detail
        assert "different document" in detail and "already gone" in detail

    def test_a_reply_that_is_already_a_tombstone_is_marked_not_deleted_again(self, tmp_path):
        app = server([thread("t1", replies=[reply("r1", deleted=True)])])
        path = write_register(tmp_path / "r.csv", [
            {"thread_id": "r1", "reply_to": "t1", "delete_comment": "TRUE"}])

        out = apply_register(app, path)
        assert "already deleted" in details(out)
        assert out["failed"] == 0

    @pytest.mark.parametrize("value, phrase", [
        pytest.param("maybe", "Use TRUE to delete this reply", id="unrecognised"),
        pytest.param("FALSE", "no way to undo", id="reversal-that-does-not-exist"),
    ])
    def test_a_reply_rows_delete_column_is_a_closed_set(self, tmp_path, value, phrase):
        """"maybe later" in a delete column must FAIL rather than be guessed at, and FALSE
        cannot mean "undelete" because Drive strips a deleted reply's text and author
        permanently. Both refusals name what to write instead."""
        app = server([thread("t1", replies=[reply("r1")])])
        path = write_register(tmp_path / "r.csv", [
            {"thread_id": "r1", "reply_to": "t1", "delete_comment": value}])

        assert phrase in details(apply_register(app, path))


class TestTheTombstoneLookupIsBestEffort:
    """When a register names a thread the live listing does not have, one more question is
    asked before calling it missing: is there a tombstone? That extra call is what keeps an
    ordinary re-run from being reported as the wrong document (#164) - and it must not be able
    to turn a readable report into an exception of its own."""

    def test_a_thread_that_is_simply_absent_is_reported_as_missing(self, tmp_path):
        """No tombstone, no comment. The register genuinely names something this file has
        never had, which is the case the different-document warning exists for."""
        app = server([thread("t1"), thread("t2"), thread("t3")])
        path = write_register(tmp_path / "r.csv", [
            {"thread_id": f"absent{i}", "resolve_comment": "TRUE"} for i in range(3)])

        out = apply_register(app, path)
        assert "different document" in out["detail"].lower()

    def test_a_tombstone_lookup_that_fails_leaves_the_row_missing_not_broken(self, tmp_path):
        """Drive answering the extra `get` with anything at all - a 500, a timeout, a
        permission change mid-run - must cost the row its tombstone check, not the report.
        Three rows, so the different-document threshold is reachable and the outcome is
        visible rather than swallowed."""
        class Backend(FakeBackend):
            def get_comment(self, file_id, comment_id, include_deleted=False):
                raise RuntimeError("Drive fell over while we were asking")

        st = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
                                "CSA_GW_PROFILE": "full"})
        backend = Backend({DOC: {"id": DOC, "name": "Draft", "mimeType": DOC_MIME}},
                          documents={DOC: {"body": {"content": []}}},
                          comments={DOC: [thread("t1"), thread("t2"), thread("t3")]})
        app = create_server(lambda: Workspace(PolicyBackend(backend, st.policy)), settings=st)
        path = write_register(tmp_path / "r.csv", [
            {"thread_id": f"absent{i}", "delete_comment": "TRUE"} for i in range(3)])

        out = apply_register(app, path)                 # must not raise
        assert "different document" in out["detail"].lower()

    def test_a_thread_listed_as_deleted_is_marked_without_deleting_it_again(self, tmp_path):
        """The other route to "already deleted": the thread IS in the live listing and carries
        Drive's deleted flag. Reached by asking for deleted comments to be included, which is
        what an export of a partly-cleaned document produces."""
        class Backend(FakeBackend):
            def list_comments(self, file_id, include_deleted=False, start_modified_time=None):
                return super().list_comments(file_id, include_deleted=True,
                                             start_modified_time=start_modified_time)

        st = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
                                "CSA_GW_PROFILE": "full"})
        backend = Backend({DOC: {"id": DOC, "name": "Draft", "mimeType": DOC_MIME}},
                          documents={DOC: {"body": {"content": []}}},
                          comments={DOC: [thread("t1", deleted=True)]})
        app = create_server(lambda: Workspace(PolicyBackend(backend, st.policy)), settings=st)
        path = write_register(tmp_path / "r.csv", [
            {"thread_id": "t1", "delete_comment": "TRUE"}])

        out = apply_register(app, path)
        assert "already deleted" in details(out)
        assert out["deleted"] == 0 and out["failed"] == 0

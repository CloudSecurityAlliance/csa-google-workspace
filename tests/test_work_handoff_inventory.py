"""A dated snapshot of one person's document footprint, for a work handoff.

Spec: `docs/superpowers/specs/2026-09-02-work-handoff-inventory.md`.

The tests worth reading are the ones about **what the artifact does not know**, because those
are the failures that look like successes:

**A partial sweep must not read as a whole one.** This library runs as a user, and the list of
ids may come from an administrator using a different tool. If 500 ids arrive and 340 are
readable, a table of 340 rows is a *lie by omission* — somebody handing over work would conclude
the other 160 files do not exist. So `unreachable` carries every one with a reason, and the first
caveat says so in words.

**Blank is not zero and not FALSE.** `comments_by_subject` is blank when comments were not
gathered, and `edited_last_by_subject` is blank when there is no subject to compare against. The
same three-state discipline `_apply.decision()` exists for, and the same failure if it breaks:
a blank read as FALSE asserts the subject did *not* touch a file nobody asked about.

**`edited_last_by_subject` is Drive's last editor.** If the subject edited and somebody else
edited afterwards, it reads FALSE — correctly, and misleadingly if a reader takes it for "never
touched this". There is a test that pins exactly that scenario, because it is the one a wrong
sweep is built on.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from csa_google_workspace import Workspace, _inventory
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.files import FileActor

DOC = "application/vnd.google-apps.document"
A = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"
B = "1ZZ2CN6VqHDjxvl9kMKXvpv5CFDf6JOkJ9U7sHoBk9y9"
SUBJECT = "away@example.org"
AWAY = {"displayName": "Away Person", "emailAddress": SUBJECT}
OTHER = {"displayName": "Someone Else", "emailAddress": "else@example.org"}
NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


def raw(file_id, **extra):
    d = {"id": file_id, "name": f"Doc {file_id[:4]}", "mimeType": DOC,
         "webViewLink": f"https://docs.google.com/document/d/{file_id}/edit",
         "modifiedTime": "2026-08-01T10:00:00Z", "createdTime": "2025-02-03T09:00:00Z"}
    d.update(extra)
    return d


def ws(files, comments=None):
    return Workspace(FakeBackend(files, comments=comments or {},
                                 documents={k: {"body": {"content": []}} for k in files}))


class TestWhatItCouldNotReachIsPartOfTheAnswer:
    """The requirement that follows from running as a user against somebody else's list."""

    def test_an_unreadable_id_is_reported_with_a_reason_not_dropped(self):
        inv = ws({A: raw(A)}).files.inventory(file_ids=[A, B], subject=SUBJECT)
        assert [r["file_id"] for r in inv.rows] == [A]
        assert len(inv.unreachable) == 1
        assert inv.unreachable[0]["file_id"] == B
        assert inv.unreachable[0]["reason"] == _inventory.NOT_FOUND

    def test_the_reason_does_not_pretend_to_know_which_it_was(self):
        """Drive answers 404 both for 'no such file' and 'you cannot see it', and this library
        cannot tell them apart. Saying `no_access` would imply the file exists; saying
        `not_found` alone would imply it does not. The detail says both."""
        inv = ws({A: raw(A)}).files.inventory(file_ids=[B])
        detail = inv.unreachable[0]["detail"]
        assert "no such file" in detail and "not visible" in detail

    def test_the_first_caveat_says_the_table_is_not_a_complete_footprint(self):
        """In words, because the count alone does not stop somebody presenting the rows as the
        whole picture - which is the actual failure mode."""
        inv = ws({A: raw(A)}).files.inventory(file_ids=[A, B])
        assert "could NOT be read" in inv.caveats[0]
        assert "complete footprint" in inv.caveats[0]

    def test_no_unreachable_means_no_such_caveat(self):
        """The counterweight: a caveat that always fires is noise, and a reader stops reading
        the list that matters."""
        inv = ws({A: raw(A)}).files.inventory(file_ids=[A])
        assert not any("could NOT be read" in c for c in inv.caveats)

    def test_one_bad_id_does_not_lose_the_others(self):
        inv = ws({A: raw(A), B: raw(B)}).files.inventory(
            file_ids=[A, "missing-1", B, "missing-2"])
        assert len(inv.rows) == 2 and len(inv.unreachable) == 2


class TestTheTwoSignalsStaySeparate:
    def test_the_subject_edited_it_last(self):
        inv = ws({A: raw(A, lastModifyingUser=AWAY)}).files.inventory(
            file_ids=[A], subject=SUBJECT)
        assert inv.rows[0]["edited_last_by_subject"] == "TRUE"
        assert inv.rows[0]["matched_on"] == "email"

    def test_somebody_edited_after_them_so_the_signal_reads_false(self):
        """**The scenario a wrong sweep is built on.** Drive reports only the LAST editor, so
        a file the subject genuinely worked on reads FALSE once anybody else touches it. The
        column is right; a reader who takes it for 'never touched this' is wrong, which is why
        the caveat spells it out and why revisions are the only complete answer."""
        inv = ws({A: raw(A, lastModifyingUser=OTHER)}).files.inventory(
            file_ids=[A], subject=SUBJECT)
        assert inv.rows[0]["edited_last_by_subject"] == "FALSE"
        assert any("never 'did they ever touch it'" in c for c in inv.caveats)

    def test_comments_are_counted_exactly(self):
        """The signal that IS exact, and the only cross-file view of somebody's commentary
        that exists - Drive has no comment predicate at all."""
        comments = {A: [{"id": "c1", "content": "x", "author": AWAY},
                        {"id": "c2", "content": "y", "author": OTHER},
                        {"id": "c3", "content": "z", "author": AWAY}]}
        inv = ws({A: raw(A)}, comments).files.inventory(file_ids=[A], subject=SUBJECT)
        assert inv.rows[0]["comments_by_subject"] == "2"

    def test_the_last_comment_time_is_the_subjects_own_latest(self):
        """Not the thread's latest and not the file's - the point of the column is "when did
        THEY last say something here", so a later comment by somebody else must not move it."""
        comments = {A: [
            {"id": "c1", "content": "early", "author": AWAY,
             "createdTime": "2026-03-01T09:00:00Z"},
            {"id": "c2", "content": "later, by someone else", "author": OTHER,
             "createdTime": "2026-08-20T09:00:00Z"},
            {"id": "c3", "content": "their latest", "author": AWAY,
             "createdTime": "2026-05-05T09:00:00Z"},
        ]}
        inv = ws({A: raw(A)}, comments).files.inventory(file_ids=[A], subject=SUBJECT)
        assert inv.rows[0]["last_comment_by_subject"].startswith("2026-05-05")

    def test_a_comment_with_no_timestamp_leaves_it_blank_rather_than_guessing(self):
        comments = {A: [{"id": "c1", "content": "x", "author": AWAY}]}
        inv = ws({A: raw(A)}, comments).files.inventory(file_ids=[A], subject=SUBJECT)
        assert inv.rows[0]["comments_by_subject"] == "1"
        assert inv.rows[0]["last_comment_by_subject"] == ""

    def test_a_file_they_never_touched_at_all_still_appears(self):
        """Absence is a finding: 'they owned it and never touched it' is worth seeing, and a
        sweep that dropped those rows would silently narrow to files with activity."""
        inv = ws({A: raw(A, lastModifyingUser=OTHER)}, {A: []}).files.inventory(
            file_ids=[A], subject=SUBJECT)
        assert inv.rows[0]["comments_by_subject"] == "0"
        assert inv.rows[0]["edited_last_by_subject"] == "FALSE"


class TestBlankIsNotZeroAndNotFalse:
    """The three-state discipline `_apply.decision()` exists for, in a second place."""

    def test_no_subject_leaves_both_signals_blank_rather_than_false(self):
        inv = ws({A: raw(A, lastModifyingUser=AWAY)}).files.inventory(file_ids=[A])
        assert inv.rows[0]["edited_last_by_subject"] == ""
        assert inv.rows[0]["comments_by_subject"] == ""

    def test_comments_not_gathered_is_blank_and_says_so(self):
        inv = ws({A: raw(A)}).files.inventory(
            file_ids=[A], subject=SUBJECT, include_comments=False)
        assert inv.rows[0]["comments_by_subject"] == ""
        assert any("blank rather than zero" in c for c in inv.caveats)


class TestIdentity:
    def test_a_display_name_match_is_recorded_as_such(self):
        """A display-name match is a guess and an email match is an identity. Recording which
        is the whole reason `matched_on` exists - `TODO.md` names this as the real problem
        sitting under the most compelling query."""
        inv = ws({A: raw(A, lastModifyingUser={"displayName": "Away Person"})}).files.inventory(
            file_ids=[A], subject="Away Person")
        assert inv.rows[0]["matched_on"] == "display_name"
        assert any("DISPLAY NAME" in c for c in inv.caveats)

    def test_email_wins_when_both_could_match(self):
        inv = ws({A: raw(A, lastModifyingUser=AWAY)}).files.inventory(
            file_ids=[A], subject=SUBJECT)
        assert inv.rows[0]["matched_on"] == "email"

    def test_a_name_only_match_caveat_is_absent_when_every_match_was_an_email(self):
        inv = ws({A: raw(A, lastModifyingUser=AWAY)}).files.inventory(
            file_ids=[A], subject=SUBJECT)
        assert not any("DISPLAY NAME" in c for c in inv.caveats)


class TestTheArtifact:
    def test_derived_columns_exist_and_are_empty(self):
        inv = ws({A: raw(A)}).files.inventory(file_ids=[A])
        for column in _inventory.DERIVED:
            assert column in inv.columns
            assert inv.rows[0][column] == ""

    def test_it_is_stamped_so_the_reader_knows_what_it_is_current_as_of(self):
        inv = _inventory.build([], now=NOW)
        assert inv.generated_at.startswith("2026-09-02T12:00:00")

    def test_the_last_caveat_states_it_is_a_snapshot_and_grants_nothing(self):
        """Two claims a reader needs and cannot infer: it will not update, and an id in the
        table is not an access path."""
        inv = ws({A: raw(A)}).files.inventory(file_ids=[A])
        assert "snapshot, not a live view" in inv.caveats[-1]
        assert "grants nothing" in inv.caveats[-1]

    def test_a_shared_drive_file_reports_its_drive_and_no_owner(self):
        """#338's reason for being a dependency: without `drive_id` a sweep mis-attributes.
        And a shared-drive file legitimately has no owner - the drive owns it."""
        inv = ws({A: raw(A, owners=[], driveId="0ABC")}).files.inventory(file_ids=[A])
        assert inv.rows[0]["drive_id"] == "0ABC"
        assert inv.rows[0]["owner_names"] == ""

    def test_repr_does_not_leak_a_file_title(self):
        """A file title can be as sensitive as its contents, and embedders log these."""
        inv = ws({A: raw(A)}).files.inventory(file_ids=[A])
        assert "Doc 1oW1" not in repr(inv)


class TestTheInput:
    def test_exactly_one_of_query_or_file_ids(self):
        files = ws({A: raw(A)}).files
        with pytest.raises(ValueError, match="exactly one"):
            files.inventory()
        with pytest.raises(ValueError, match="exactly one"):
            files.inventory(query="name contains 'x'", file_ids=[A])

    def test_the_query_path_works_too(self):
        inv = ws({A: raw(A), B: raw(B)}).files.inventory(query="name contains 'Doc'")
        assert len(inv.rows) == 2 and inv.unreachable == []

    def test_limit_bounds_the_id_list(self):
        inv = ws({A: raw(A), B: raw(B)}).files.inventory(file_ids=[A, B], limit=1)
        assert len(inv.rows) == 1


def test_a_matcher_ignores_an_empty_subject():
    """`_matches` is the one place a blank could silently match everything."""
    assert _inventory._matches(FileActor("X", "x@y"), "   ") is None
    assert _inventory._matches(None, "x@y") is None

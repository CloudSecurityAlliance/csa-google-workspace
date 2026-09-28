"""The refusals in `workspace.files` - the arguments this library will not pass to Drive.

Every one of these is a `ValueError` raised BEFORE the API call, and they divide into two
kinds that deserve to be told apart:

* **Refusals of the irreversible.** `role="owner"` transfers ownership of a file. Drive gives
  no way to undo it from here, and the new owner can remove the old one - so the library
  declines and names the deliberate route, rather than offering it behind a string.
* **Refusals of the meaningless.** An empty name, an address with no `@`, content of the wrong
  type for the kind of file. Drive accepts several of these and produces something nobody
  wanted, which is worse than an error because it looks like it worked.

They were untested together, which made the first kind indistinguishable from the second.
"""
from __future__ import annotations

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace import exceptions as exc
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"
FILES = {"f": {"id": "f", "name": "D", "mimeType": DOC, "webViewLink": "u"}}


@pytest.fixture
def files():
    return Workspace(FakeBackend(dict(FILES))).files


class TestOwnershipIsNotTransferredFromHere:
    """The one role this library will not grant, in either of the two places it could be."""

    def test_share_refuses_owner_and_names_the_deliberate_route(self, files):
        with pytest.raises(ValueError, match="will not transfer ownership"):
            files.share("f", "someone@example.org", role="owner")

    def test_set_role_refuses_owner_too(self, files):
        """Both entry points, because a refusal on one of two doors is a door."""
        with pytest.raises(ValueError, match="will not transfer ownership"):
            files.set_role("f", "perm-1", role="owner")

    def test_share_offers_writer_as_the_thing_owner_is_usually_meant_for(self, files):
        """The message has to say what to do instead. "Full edit access" is what somebody
        reaching for `owner` almost always wants, and it is reversible."""
        with pytest.raises(ValueError, match="writer"):
            files.share("f", "someone@example.org", role="owner")


class TestUnknownRolesAreRefusedRatherThanSent:
    @pytest.mark.parametrize("role", ["editor", "READER", "admin", ""])
    def test_share_names_the_roles_that_exist(self, files, role):
        """Drive's roles are a closed set with exact spellings. "editor" is the Docs UI's word
        and not an API role; "READER" is the right word in the wrong case. Sending either gets
        a 400 from Drive that names neither the argument nor the alternatives."""
        with pytest.raises(ValueError, match="unknown role"):
            files.share("f", "someone@example.org", role=role)

    def test_set_role_names_them_too(self, files):
        with pytest.raises(ValueError, match="unknown role"):
            files.set_role("f", "perm-1", role="editor")

    def test_the_message_lists_what_is_accepted(self, files):
        from csa_google_workspace.permissions import ROLES

        with pytest.raises(ValueError) as ei:
            files.share("f", "a@b.c", role="nonsense")
        for role in ROLES:
            assert role in str(ei.value), "a refusal that does not list the alternatives"


class TestAddressesAndNames:
    @pytest.mark.parametrize("email", ["", "not-an-address", "someone"])
    def test_an_address_without_an_at_sign_is_refused(self, files, email):
        """Drive accepts a malformed address on a permission and the grant then exists,
        pointing at nobody. A permission nobody holds is worse than an error, because
        `get_file_permissions` lists it and it reads as access somebody has."""
        with pytest.raises(ValueError, match="expected an email address"):
            files.share("f", email)

    @pytest.mark.parametrize("name", ["", "   ", "\t\n"])
    def test_renaming_to_nothing_is_refused(self, files, name):
        """Drive accepts an empty name and the file becomes untitled - findable only by id,
        which is exactly what somebody renaming a file does not have."""
        with pytest.raises(ValueError, match="cannot be empty"):
            files.update("f", name=name)

    def test_a_name_that_is_merely_unusual_is_allowed(self, files):
        """The guard is against EMPTY, not against odd. A file called "." is somebody's
        choice; refusing it would be this library inventing a naming policy."""
        assert files.update("f", name=".").name == "."


class TestCreatingAFile:
    def test_an_unknown_kind_lists_the_kinds_that_exist(self, files):
        from csa_google_workspace.files import KINDS

        with pytest.raises(ValueError) as ei:
            files.create("N", "presentation-deck")
        for kind in KINDS:
            assert kind in str(ei.value)

    def test_content_is_refused_for_a_kind_that_cannot_take_it(self, files):
        """Uploading content CONVERTS a file, and the conversion is per-kind. Accepting the
        argument and dropping it would create an empty file and report success."""
        with pytest.raises(ValueError, match="content is not supported"):
            files.create("N", "folder", content="some text")

    def test_content_of_the_wrong_type_names_both_types(self, files):
        """`str` where `bytes` are wanted, or the reverse. The message names what the kind
        expects AND what arrived, because the mistake is usually one call up."""
        with pytest.raises(ValueError) as ei:
            files.create("N", "spreadsheet", content="a,b,c")
        message = str(ei.value)
        assert "spreadsheet" in message and "str" in message

    def test_a_document_takes_text(self, files):
        assert files.create("N", "document", content="hello").id


class TestDriveAnsweringInAShapeNobodyExpected:
    """`unknown beats wrong` - the rule these two helpers exist to apply.

    Both are parsers over fields Drive has always sent in one shape. If that ever changes, the
    choice is between a plausible-looking wrong value and an absent one, and an absent one is
    the only honest answer: a modification time that silently became 1970 sorts a file to the
    bottom of a recency list and nothing anywhere says why.
    """

    @pytest.mark.parametrize("value", ["not a date", "2026-13-45T99:99:99Z", ""])
    def test_an_unparseable_timestamp_is_none(self, value):
        from csa_google_workspace.files import _parse_time

        assert _parse_time(value) is None

    def test_a_real_timestamp_still_parses(self):
        from csa_google_workspace.files import _parse_time

        parsed = _parse_time("2026-09-27T12:00:00Z")
        assert parsed is not None and parsed.year == 2026

    @pytest.mark.parametrize("value", ["not a number", None, [], {}])
    def test_a_size_that_is_not_a_number_is_none(self, value):
        from csa_google_workspace.files import _parse_size

        assert _parse_size(value) is None

    def test_drives_own_string_sizes_still_parse(self):
        """Drive sends `size` as a STRING of digits, so the conversion is the normal path
        rather than the exceptional one."""
        from csa_google_workspace.files import _parse_size

        assert _parse_size("1024") == 1024


class TestOneBadFileDoesNotLoseTheOthers:
    """`inventory` over explicit ids. A run of 500 with one bad id has to return 499 rows and
    say what happened to the one - the alternative is an exception that loses the work."""

    @staticmethod
    def collection(raiser):
        class Backend(FakeBackend):
            def get_file_metadata(self, file_id):
                if file_id == "bad":
                    raise raiser
                return super().get_file_metadata(file_id)

        return Workspace(Backend(dict(FILES))).files

    @pytest.mark.parametrize("error, reason, phrase", [
        pytest.param(exc.NotFoundError("gone"), "not_found", "no such file", id="not-found"),
        pytest.param(exc.AccessError("nope"), "no_access", "not permitted", id="no-access"),
        pytest.param(exc.ApiError(500, "backendError", "try again later"), "failed", "backendError",
                     id="api-error"),
    ])
    def test_each_failure_is_recorded_with_its_own_reason(self, error, reason, phrase):
        """Three reasons, not one. "not_found" implies the file does not exist and "no_access"
        implies it does - guessing between them would state something about somebody's Drive
        that this account cannot actually know."""
        inv = self.collection(error).inventory(file_ids=["f", "bad"])

        assert inv.reached == 1, "the good file is still in the table"
        assert len(inv.unreachable) == 1
        entry = inv.unreachable[0]
        assert entry["file_id"] == "bad" and entry["reason"] == reason
        assert phrase in entry["detail"]

    def test_an_api_error_detail_is_truncated_rather_than_unbounded(self):
        """It goes into a table cell. A backend error carrying a kilobyte of HTML would make
        the row unreadable and the CSV unusable."""
        inv = self.collection(
            exc.ApiError(500, "backendError", "x" * 5000)).inventory(file_ids=["bad"])
        assert len(inv.unreachable[0]["detail"]) <= 200


class TestCountingCommentsAcrossAnInventory:
    """`include_comments=True` opens every file in the table. Two things go wrong there, and
    neither is a reason to lose the table."""

    PDF = {"id": "pdf", "name": "Scan", "mimeType": "application/pdf", "webViewLink": "u"}
    FOLDER = {"id": "dir", "name": "Box",
              "mimeType": "application/vnd.google-apps.folder", "webViewLink": "u"}

    def test_a_file_with_no_comment_surface_is_skipped_not_failed(self):
        """A PDF and a folder have no Drive comments to read. Attempting it would raise, and
        recording them as unreachable would say the ROW is bad when only the count is."""
        backend = FakeBackend({**FILES, "pdf": self.PDF, "dir": self.FOLDER})
        inv = Workspace(backend).files.inventory(
            file_ids=["f", "pdf", "dir"], subject="everything", include_comments=True)

        assert inv.reached == 3, "all three files are still in the table"
        assert inv.unreachable == []

    def test_a_file_whose_comments_cannot_be_read_keeps_its_row(self):
        """Listable, and its comments are not - a real Drive state, and a sharply different
        one from "the file is unreachable". The row is real, so it stays; the count goes blank
        and the caveat explains blank."""
        class Backend(FakeBackend):
            def list_comments(self, file_id, **kw):
                raise exc.AccessError("comments are restricted on this file")

        inv = Workspace(Backend(dict(FILES))).files.inventory(
            file_ids=["f"], subject="everything", include_comments=True)

        assert inv.reached == 1
        assert inv.unreachable == [], "the FILE was reachable; only its comments were not"

"""The optional arguments on `ApiBackend`'s writes - the arms nothing was passing.

`test_apibackend_contract.py` calls every write once, with the minimum that reaches
`_errors.call`. That proves the retry flag and the error translation, and it leaves every
`if optional_thing:` inside those methods unexecuted.

Those arms are where an argument gets silently dropped. A dropped `parent_id` puts a new file
in the Drive root instead of the folder somebody named; a dropped `removeParents` turns a MOVE
into a copy that lives in two places; a dropped `tabId` deletes a range from the wrong tab of a
document. All three succeed, return a plausible-looking response, and do the wrong thing.

So the assertions are on the REQUEST: what would have been sent to Google. A recorder stands in
for the client and keeps every call's keywords, because the request is the only place the
argument is observable before it reaches Drive.
"""
from __future__ import annotations

import pytest

from csa_google_workspace.backend import ApiBackend


class Recorder:
    """Any attribute, any call, returning itself - and keeping every call's keywords.

    `ApiBackend` builds a request by chaining (`drive.files().update(**kw).execute`), so the
    keywords of interest belong to whichever call in the chain carried them. Recording them all
    and searching means a test does not have to know the chain's shape.
    """

    def __init__(self):
        self.calls: list[dict] = []

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self

    def __call__(self, *args, **kwargs):
        if kwargs:
            self.calls.append(kwargs)
        return self

    def execute(self):
        return {}

    def sent(self) -> dict:
        """Every keyword sent anywhere in the chain, merged."""
        merged: dict = {}
        for call in self.calls:
            merged.update(call)
        return merged


@pytest.fixture
def backend():
    recorder = Recorder()
    return ApiBackend(recorder), recorder


class TestCreatingAFile:
    def test_a_parent_is_sent_as_the_new_files_parents(self, backend):
        """Dropped, the file lands in the Drive root. It succeeds, returns an id, and the
        person looking in the folder they named finds nothing."""
        api, recorder = backend
        api.create_file("Notes", "application/vnd.google-apps.document", parent_id="folder1")
        assert recorder.sent()["body"]["parents"] == ["folder1"]

    def test_no_parent_sends_no_parents_key_at_all(self, backend):
        """Absent, not empty. `"parents": []` is a different request, and Drive has rejected
        malformed parent lists rather than ignoring them."""
        api, recorder = backend
        api.create_file("Notes", "application/vnd.google-apps.document")
        assert "parents" not in recorder.sent()["body"]

    def test_content_is_uploaded_with_its_own_source_type(self, backend):
        """The two mime types are DIFFERENT on purpose: `body.mimeType` is the target and the
        upload's is the source, and Drive converts between them. That is how `text/markdown`
        becomes a real Doc rather than a Doc containing the characters of some markdown."""
        api, recorder = backend
        api.create_file("Notes", "application/vnd.google-apps.document",
                        content=b"# Heading", content_mime_type="text/markdown")
        sent = recorder.sent()

        assert sent["body"]["mimeType"] == "application/vnd.google-apps.document"
        assert sent["media_body"].mimetype() == "text/markdown"

    def test_no_content_sends_no_media_body(self, backend):
        api, recorder = backend
        api.create_file("Notes", "application/vnd.google-apps.document")
        assert "media_body" not in recorder.sent()


class TestMovingAndRenaming:
    def test_adding_a_parent_without_removing_one_leaves_the_file_in_both(self, backend):
        """Drive's own semantics, and the reason `remove_parent_id` exists as a separate
        argument rather than being inferred: `addParents` alone ADDS a location."""
        api, recorder = backend
        api.update_file_metadata("f", add_parent="folder2")
        sent = recorder.sent()

        assert sent["addParents"] == "folder2"
        assert "removeParents" not in sent, "an add must not silently become a move"

    def test_a_move_sends_both_halves(self, backend):
        """Dropping `removeParents` turns a move into a copy that lives in two folders - which
        looks correct from the destination and wrong from everywhere else."""
        api, recorder = backend
        api.update_file_metadata("f", add_parent="to", remove_parent="from")
        sent = recorder.sent()

        assert sent["addParents"] == "to" and sent["removeParents"] == "from"

    def test_a_rename_alone_touches_no_parents(self, backend):
        api, recorder = backend
        api.update_file_metadata("f", name="New name")
        sent = recorder.sent()

        assert sent["body"] == {"name": "New name"}
        assert "addParents" not in sent and "removeParents" not in sent

    def test_copying_can_name_and_place_the_copy(self, backend):
        api, recorder = backend
        api.copy_file("f", name="A copy", parent_id="folder3")
        body = recorder.sent()["body"]

        assert body["name"] == "A copy" and body["parents"] == ["folder3"]

    def test_copying_with_neither_sends_an_empty_body(self, backend):
        """So Drive applies its own defaults - "Copy of X", same folder - rather than this
        library guessing at them."""
        api, recorder = backend
        api.copy_file("f")
        assert recorder.sent()["body"] == {}


class TestTabsAndRanges:
    def test_a_new_sheet_tab_can_be_positioned(self, backend):
        """Without `index` Google appends. With it, the tab lands where a register build
        expects it - and a dropped index silently reorders somebody's workbook."""
        api, recorder = backend
        api.sheets_add_tab("f", "Register", index=0)
        body = recorder.sent()["body"]
        props = body["requests"][0]["addSheet"]["properties"]

        assert props == {"title": "Register", "index": 0}

    def test_without_an_index_none_is_sent(self, backend):
        """`"index": None` is not the same as omitting it, and Sheets rejects a null."""
        api, recorder = backend
        api.sheets_add_tab("f", "Register")
        props = recorder.sent()["body"]["requests"][0]["addSheet"]["properties"]

        assert props == {"title": "Register"}

    def test_deleting_a_range_can_name_the_tab_it_is_in(self, backend):
        """A Doc with tabs has the same index space repeated per tab. Dropping `tabId` deletes
        the same character offsets out of whichever tab Docs defaults to - which is a deletion
        from the wrong tab that reports success."""
        api, recorder = backend
        api.docs_delete_range("f", 5, 10, tab_id="t.2")
        request = recorder.sent()["body"]["requests"][0]["deleteContentRange"]["range"]

        assert request == {"startIndex": 5, "endIndex": 10, "tabId": "t.2"}

    def test_without_a_tab_id_the_range_carries_none(self, backend):
        api, recorder = backend
        api.docs_delete_range("f", 5, 10)
        request = recorder.sent()["body"]["requests"][0]["deleteContentRange"]["range"]

        assert request == {"startIndex": 5, "endIndex": 10}


class TestResolvingAnAccessProposal:
    def test_accepting_sends_the_roles_that_were_decided(self, backend):
        """The requester does not choose their own access level. Dropping `role` would let
        Drive apply whatever the PROPOSAL asked for - which is attacker-controlled input in
        the one place it decides who gets access."""
        api, recorder = backend
        api.resolve_access_proposal("f", "ap1", action="ACCEPT", roles=["reader"])
        body = recorder.sent()["body"]

        assert body["action"] == "ACCEPT" and body["role"] == ["reader"]

    def test_a_view_is_sent_when_one_was_chosen(self, backend):
        api, recorder = backend
        api.resolve_access_proposal("f", "ap1", action="ACCEPT", roles=["commenter"],
                                    view="published")
        assert recorder.sent()["body"]["view"] == "published"

    def test_denying_sends_neither_a_role_nor_a_view(self, backend):
        """A denial grants nothing. A role on a deny is at best ignored and at worst applied,
        and the request is the only place to be sure which."""
        api, recorder = backend
        api.resolve_access_proposal("f", "ap1", action="DENY")
        body = recorder.sent()["body"]

        assert body["action"] == "DENY"
        assert "role" not in body and "view" not in body


class TestReplies:
    def test_a_reply_can_carry_an_action(self, backend):
        """`resolve` and `reopen` are replies with an `action`, not separate endpoints. A
        dropped action posts an empty-looking reply and leaves the thread open."""
        api, recorder = backend
        api.create_reply("f", "c1", content="Done", action="resolve")
        body = recorder.sent()["body"]

        assert body["content"] == "Done" and body["action"] == "resolve"

    def test_a_plain_reply_sends_no_action(self, backend):
        api, recorder = backend
        api.create_reply("f", "c1", content="Just a note")
        assert "action" not in recorder.sent()["body"]

    def test_an_action_with_no_content_sends_only_the_action(self, backend):
        """Resolving without saying anything. `"content": ""` would post an empty reply
        visible to everybody on the thread."""
        api, recorder = backend
        api.create_reply("f", "c1", action="resolve")
        body = recorder.sent()["body"]

        assert body == {"action": "resolve"}


class TestAPermissionWithNoAddress:
    """`email=None` is not a missing argument - it is a LINK SHARE.

    A permission of type `anyone` has no address, because there is nobody in particular to
    name. It is the broadest grant Drive offers, and it is expressed here by the ABSENCE of a
    field, which makes it the one case where "the argument was dropped" and "the caller meant
    this" look identical in the request.
    """

    def test_a_link_share_sends_no_email_address_field(self, backend):
        api, recorder = backend
        api.create_permission("f", email=None, role="reader", permission_type="anyone")
        body = recorder.sent()["body"]

        assert body["type"] == "anyone" and body["role"] == "reader"
        assert "emailAddress" not in body, "Drive rejects an address on an `anyone` permission"

    def test_a_named_grant_still_carries_the_address(self, backend):
        api, recorder = backend
        api.create_permission("f", email="someone@example.org", role="writer")
        body = recorder.sent()["body"]

        assert body["emailAddress"] == "someone@example.org"
        assert body["type"] == "user"

    def test_the_recipient_is_notified_unless_told_otherwise(self, backend):
        """`sendNotificationEmail` defaults to True on purpose: a share the recipient is told
        about is a share somebody can notice and question. Silent grants are how access
        accumulates unobserved."""
        api, recorder = backend
        api.create_permission("f", email="someone@example.org", role="reader")
        assert recorder.sent()["sendNotificationEmail"] is True

    def test_suppressing_the_notification_is_explicit(self, backend):
        api, recorder = backend
        api.create_permission("f", email="someone@example.org", role="reader", notify=False)
        assert recorder.sent()["sendNotificationEmail"] is False


class TestAddingADocTab:
    def test_a_title_is_sent_as_tab_properties(self, backend):
        api, recorder = backend
        api.docs_add_tab("f", "Appendix")
        request = recorder.sent()["body"]["requests"][0]["addDocumentTab"]

        assert request == {"tabProperties": {"title": "Appendix"}}

    def test_no_title_sends_an_empty_request_so_google_names_it(self, backend):
        """Measured: Google auto-titles ("Tab 2") and assigns the index when neither is given.
        Sending `{"tabProperties": {"title": None}}` instead would be a request for a tab
        called nothing."""
        api, recorder = backend
        api.docs_add_tab("f")
        assert recorder.sent()["body"]["requests"][0]["addDocumentTab"] == {}

"""ApiBackend behaviors that FakeBackend cannot exercise (audit findings #6, #7):
comment-list pagination, and the non-idempotent wiring on every write method.
Both are only otherwise covered by the never-in-CI live suite.
"""
import pytest

from csa_google_workspace.backend import ApiBackend

# --- #6: list_comments must follow nextPageToken and preserve filters ----------

class _Request:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class _PagedComments:
    def __init__(self, pages):
        self._pages = pages
        self._i = 0
        self.calls = []          # kwargs of each list() call, in order

    def list(self, **kwargs):
        self.calls.append(kwargs)
        page = self._pages[self._i]
        self._i += 1
        return _Request(page)


class _Drive:
    def __init__(self, comments):
        self._comments = comments

    def comments(self):
        return self._comments


class _Services:
    def __init__(self, comments):
        self.drive = _Drive(comments)


def test_list_comments_paginates_and_preserves_filters():
    paged = _PagedComments([
        {"comments": [{"id": "c1"}, {"id": "c2"}], "nextPageToken": "tok"},
        {"comments": [{"id": "c3"}]},   # no nextPageToken -> stop
    ])
    backend = ApiBackend(_Services(paged))

    out = backend.list_comments("file1", include_deleted=True,
                                start_modified_time="2026-01-01T00:00:00Z")

    assert [c["id"] for c in out] == ["c1", "c2", "c3"]     # all pages, not truncated
    assert len(paged.calls) == 2
    assert "pageToken" not in paged.calls[0]                # first call: no token
    assert paged.calls[1]["pageToken"] == "tok"             # second: carried the token
    # filters preserved across pages
    assert paged.calls[0]["includeDeleted"] is True and paged.calls[1]["includeDeleted"] is True
    assert paged.calls[0]["startModifiedTime"] == "2026-01-01T00:00:00Z"
    assert paged.calls[1]["startModifiedTime"] == "2026-01-01T00:00:00Z"


# --- #7: every write must pass idempotent=False so 5xx never double-applies -----

class _Chain:
    """Accepts any attribute access and any call, returning itself; .execute() -> {}.
    Lets each write method build its request without a real Google client."""
    def __getattr__(self, name):
        return self

    def __call__(self, *args, **kwargs):
        return self

    def execute(self):
        return {}


# DERIVED from policy._GATES, not hand-listed (#324). The call-by-call version exercised 15 of
# 26 MODIFY-gated writes, and the eleven it missed included `create_permission` - the SHARING
# write, where a silently retried 5xx that had already landed is a duplicated grant of access.
# A write added to `ApiBackend` without the `idempotent=False` flag gains a retry that can
# double-apply, and nothing would have said so.
#
# Two are excluded because they never reach `_errors.call` at all: `ApiBackend` raises
# `UnsupportedOperation` for both, so there is no request to flag. Declared rather than filtered
# by behaviour, so that if either ever becomes real the assertion below fails and somebody adds
# the call deliberately - which matters, because both now EXIST in Google's Developer Preview
# (see research/comments-apis-2026-09.md).
NOT_IMPLEMENTED_SO_NO_REQUEST = {
    "accept_suggestion": "ApiBackend raises UnsupportedOperation; no HTTP call is made",
    "create_cell_anchored_comment": "same - the GA API cannot anchor a comment to a cell",
}

# How to call each write with arguments that reach `_errors.call`. Hand-written, because a
# derived call cannot know what a valid argument looks like - but WHICH writes must appear is
# derived, which is the half that used to fall behind.
WRITE_CALLS = {
    "create_comment":               lambda b: b.create_comment("f", "hi"),
    "create_reply":                 lambda b: b.create_reply("f", "c", content="x"),
    "update_comment":               lambda b: b.update_comment("f", "c", "x"),
    "update_reply":                 lambda b: b.update_reply("f", "c", "r", "x"),
    "delete_comment":               lambda b: b.delete_comment("f", "c"),
    "delete_reply":                 lambda b: b.delete_reply("f", "c", "r"),
    "docs_batch_update":            lambda b: b.docs_batch_update("f", []),
    "sheets_values_update":         lambda b: b.sheets_values_update("f", "A1", [[1]]),
    "sheets_values_append":         lambda b: b.sheets_values_append("f", "A1", [[1]]),
    "sheets_values_clear":          lambda b: b.sheets_values_clear("f", "A1"),
    "sheets_batch_update":          lambda b: b.sheets_batch_update("f", []),
    "slides_batch_update":          lambda b: b.slides_batch_update("f", []),
    # #235: both permission mutations. `delete_permission` matters most - it returns None, so a
    # retried 5xx that already landed looks like a clean second revocation rather than an error,
    # and the caller never learns the first one worked.
    "update_permission":            lambda b: b.update_permission("f", "p1", role="reader"),
    "delete_permission":            lambda b: b.delete_permission("f", "p1"),
    # Answering an access request. Returns None like `delete_permission`, so a retried 5xx that
    # had already landed looks like a clean second resolve - and the mutation it may have already
    # applied is A GRANT OF ACCESS. Worst thing here to double-apply silently.
    "resolve_access_proposal":      lambda b: b.resolve_access_proposal(
                                        "f", "ap1", action="ACCEPT", roles=["reader"]),
    # ADDED BY #324. `create_permission` is the one the hand-list omitted and the one whose
    # repetition is most visible to a third party: a second grant to the same address.
    "create_permission":            lambda b: b.create_permission(
                                        "f", email="a@b.com", role="reader"),
    "create_file":                  lambda b: b.create_file("n", "text/plain"),
    "trash_file":                   lambda b: b.trash_file("f"),
    "update_file_metadata":         lambda b: b.update_file_metadata("f", name="n"),
    "docs_add_tab":                 lambda b: b.docs_add_tab("f", "t"),
    "docs_delete_range":            lambda b: b.docs_delete_range("f", 1, 2),
    "docs_delete_tab":              lambda b: b.docs_delete_tab("f", "t1"),
    "sheets_add_tab":               lambda b: b.sheets_add_tab("f", "t"),
    "sheets_delete_tab":            lambda b: b.sheets_delete_tab("f", 0),
}


def _modify_gated() -> set[str]:
    from csa_google_workspace.policy import _GATES, MODIFY
    return {m for m, g in _GATES.items() if g.access == MODIFY}


def test_every_write_is_exercised_by_this_file():
    """The guard on the guard. Without it, a new write simply is not tested and nothing says so
    - which is how this file came to cover 15 of 26."""
    expected = _modify_gated() - set(NOT_IMPLEMENTED_SO_NO_REQUEST)
    missing = sorted(expected - set(WRITE_CALLS))
    assert missing == [], (
        f"these writes are MODIFY-gated and never called here: {missing}. Add a lambda to "
        f"WRITE_CALLS - a write with no test can silently gain a retry that double-applies.")
    extra = sorted(set(WRITE_CALLS) - _modify_gated())
    assert extra == [], f"WRITE_CALLS names non-write methods: {extra}"


def test_the_exclusions_are_still_unimplemented():
    """Both now exist in Google's Developer Preview. If either becomes reachable here, the
    exclusion is wrong and this says so rather than leaving a write untested."""
    from csa_google_workspace import exceptions as exc
    from csa_google_workspace.backend import ApiBackend
    b = ApiBackend(_Chain())
    for name in NOT_IMPLEMENTED_SO_NO_REQUEST:
        with pytest.raises(exc.UnsupportedOperation):
            getattr(b, name)("f", "x") if name == "accept_suggestion" else \
                getattr(b, name)("f", "A1", "x")


def test_all_writes_are_non_idempotent(monkeypatch):
    """Only 429 is retried for a non-idempotent call; 5xx is not, because the mutation may
    already have landed server-side. A write that omits the flag silently gains a retry that
    can double-apply — CLAUDE.md invariant 1."""
    captured: dict[str, bool] = {}

    def fake_call(fn, *args, idempotent=True, _sleep=None, **kwargs):
        captured[_current[0]] = idempotent
        return {}

    monkeypatch.setattr("csa_google_workspace.backend._errors.call", fake_call)
    b = ApiBackend(_Chain())
    _current = [""]
    for name, call in sorted(WRITE_CALLS.items()):
        _current[0] = name
        call(b)

    wrong = sorted(n for n, flag in captured.items() if flag is not False)
    assert wrong == [], (
        f"these writes did NOT pass idempotent=False: {wrong}. Each can be retried after a 5xx "
        f"and applied twice.")
    assert len(captured) == len(WRITE_CALLS), (
        f"only {len(captured)} of {len(WRITE_CALLS)} writes reached _errors.call")


class _FilesStub:
    """Minimal drive.files() double. The module's other stubs are shaped for comments()."""

    def __init__(self, result):
        self.result = result
        self.calls: dict = {}

    def list(self, **kwargs):
        self.calls.update(kwargs)
        return _Request(self.result)


class _DriveWithFiles:
    def __init__(self, files):
        self._files = files

    def files(self):
        return self._files


class _ServicesWithFiles:
    def __init__(self, files):
        self.drive = _DriveWithFiles(files)


def test_search_files_sends_the_query_and_shared_drive_flags():
    """`ApiBackend` is the only place the real Drive query string is built, and FakeBackend
    is deliberately not a Drive query engine — so the wiring is asserted here.

    includeItemsFromAllDrives/supportsAllDrives are not optional polish: shared drives are
    where collaborative review happens, and omitting them silently hides every file in one.
    """
    files = _FilesStub({"files": [{"id": "a"}], "nextPageToken": "t2"})
    out = ApiBackend(_ServicesWithFiles(files)).search_files(
        "name contains 'x'", page_size=7, order_by="modifiedTime desc", page_token="t1")

    assert out["files"] == [{"id": "a"}]
    assert files.calls["q"] == "name contains 'x'"
    assert files.calls["pageSize"] == 7
    assert files.calls["orderBy"] == "modifiedTime desc"
    assert files.calls["pageToken"] == "t1"
    assert files.calls["includeItemsFromAllDrives"] is True
    assert files.calls["supportsAllDrives"] is True
    assert "webViewLink" in files.calls["fields"]
    assert "nextPageToken" in files.calls["fields"]


def test_get_sheet_notes_asks_for_notes_and_NOT_for_cell_values():
    """The field mask is the whole reason this is a separate call, and it lives only in
    `ApiBackend` — `FakeBackend` returns a fixture and cannot cover it.

    `rowData(values(note))` fetches note text and **no cell values**, so counting notes on a
    large sheet costs one small request. Asking for `rowData(values)` whole would pull the
    entire grid, which is why `get_spreadsheet` was not simply widened: every `list_tabs` would
    then pay for notes it never reads.
    """
    class _Sheets:
        def __init__(self): self.calls = {}
        def spreadsheets(self): return self
        def get(self, **kw): self.calls = kw; return self
        def execute(self): return {"sheets": []}
    class _Services:
        def __init__(self, s): self.sheets = s

    sheets = _Sheets()
    ApiBackend(_Services(sheets)).get_sheet_notes("f1")
    fields = sheets.calls["fields"]
    assert "rowData(values(note))" in fields.replace(" ", "")
    assert "formattedValue" not in fields and "effectiveValue" not in fields, (
        "the mask must not pull cell values - that is what makes counting notes cheap")


def test_search_asks_drive_for_the_facts_an_inventory_needs():
    """The field list lives only in `ApiBackend`, so `FakeBackend` cannot cover it — it just
    hands back whatever a fixture put in the dict. That is precisely the fake/real blind spot
    CLAUDE.md invariant 4 names, and the cost of missing it here is silent: every field would
    read as `None`, which this library defines as "not asked for", so an inventory would
    report ownership as unknown for every file and look like it was working.
    """
    files = _FilesStub({"files": []})
    ApiBackend(_ServicesWithFiles(files)).search_files("q")
    fields = files.calls["fields"]
    for wanted in ("createdTime", "owners(", "lastModifyingUser(", "driveId"):
        assert wanted in fields, f"search does not ask Drive for {wanted}"


def test_the_user_sub_selection_does_not_drag_in_unread_personal_data():
    """`owners` and `lastModifyingUser` are sub-selected to three fields rather than taken
    whole. Drive's full `User` also carries `photoLink` and `permissionId`, which nothing in
    this library reads — so asking for them would move a third party's personal data into a
    model's context for no reason. Asserted because `owners` (no parens) is the shorter thing
    to write and would work.
    """
    files = _FilesStub({"files": []})
    ApiBackend(_ServicesWithFiles(files)).search_files("q")
    fields = files.calls["fields"]
    assert "photoLink" not in fields and "permissionId" not in fields
    assert "owners(displayName,emailAddress,me)" in fields.replace(" ", "")


def test_search_files_omits_order_by_and_page_token_when_unset():
    """Sending orderBy=None is not the same as omitting it; Drive rejects the former."""
    files = _FilesStub({"files": []})
    ApiBackend(_ServicesWithFiles(files)).search_files("q")
    assert "orderBy" not in files.calls and "pageToken" not in files.calls


class _PermsStub:
    """drive.permissions() double. Pages, and records every call's kwargs."""

    def __init__(self, pages):
        self._pages = pages; self._i = 0; self.calls: list[dict] = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        page = self._pages[self._i]; self._i += 1
        return _Request(page)


class _DriveWithPerms:
    def __init__(self, perms): self._perms = perms

    def permissions(self): return self._perms


class _ServicesWithPerms:
    def __init__(self, perms): self.drive = _DriveWithPerms(perms)


def test_list_permissions_follows_pagination_and_asks_for_the_pii_fields():
    """The default permissions.list response omits emailAddress and displayName, which are
    the entire point of the call. And supportsAllDrives is not optional: a file on a shared
    drive otherwise reports no permissions at all.

    FakeBackend cannot cover either — it has no pages and no `fields` — which is why this
    lives in the ApiBackend contract suite (CLAUDE.md invariant 4).
    """
    perms = _PermsStub([
        {"permissions": [{"id": "p1"}], "nextPageToken": "n1"},
        {"permissions": [{"id": "p2"}]},
    ])
    out = ApiBackend(_ServicesWithPerms(perms)).list_permissions("f")

    assert [p["id"] for p in out] == ["p1", "p2"]
    assert len(perms.calls) == 2
    assert perms.calls[0]["fileId"] == "f"
    assert "emailAddress" in perms.calls[0]["fields"]
    assert "displayName" in perms.calls[0]["fields"]
    assert perms.calls[0]["supportsAllDrives"] is True
    assert "pageToken" not in perms.calls[0]
    assert perms.calls[1]["pageToken"] == "n1"


# --- #235: the permission mutations, against a stub Drive service -----------------
#
# `FakeBackend` cannot catch a wrong field name, a missing `supportsAllDrives`, or a body built
# in the wrong shape - it never sees the request. That is the documented blind spot of the
# fake/real seam, and it is exactly how `Workspace.open()` once leaked a raw `HttpError` past a
# fully green suite.

class _RecordingPerms:
    def __init__(self):
        self.calls = []

    def update(self, **kw):
        self.calls.append(("update", kw))
        return _Chain()

    def delete(self, **kw):
        self.calls.append(("delete", kw))
        return _Chain()


class _DriveRecording:
    def __init__(self, perms):
        self._perms = perms

    def permissions(self):
        return self._perms


class _ServicesRecording:
    def __init__(self, perms):
        self.drive = _DriveRecording(perms)


def test_update_permission_sends_only_the_role_and_supports_shared_drives():
    perms = _RecordingPerms()
    ApiBackend(_ServicesRecording(perms)).update_permission("f1", "p9", role="reader")
    (name, kw), = perms.calls
    assert name == "update"
    assert kw["fileId"] == "f1" and kw["permissionId"] == "p9"
    assert kw["body"] == {"role": "reader"}, (
        "the body must carry the role and nothing else - sending `type` or `emailAddress` on an "
        "update is how a downgrade quietly becomes a different grant")
    assert kw["supportsAllDrives"] is True, (
        "without this the call fails on any shared drive, which is where shared documents live")


def test_delete_permission_sends_no_body_and_supports_shared_drives():
    perms = _RecordingPerms()
    ApiBackend(_ServicesRecording(perms)).delete_permission("f1", "p9")
    (name, kw), = perms.calls
    assert name == "delete"
    assert kw == {"fileId": "f1", "permissionId": "p9", "supportsAllDrives": True}


def test_update_permission_asks_for_the_fields_the_model_needs_back():
    """A downgrade that returns no role leaves the caller unable to confirm what it achieved."""
    perms = _RecordingPerms()
    ApiBackend(_ServicesRecording(perms)).update_permission("f1", "p9", role="commenter")
    fields = perms.calls[0][1]["fields"]
    for wanted in ("id", "role", "type"):
        assert wanted in fields


# --- accessproposals: pagination, and the body `resolve` actually sends ------------
#
# Both invisible to `FakeBackend`, which never sees a request (CLAUDE.md invariant 4).


class _ProposalsStub:
    def __init__(self, pages):
        self._pages, self._i = pages, 0
        self.list_calls, self.resolve_calls = [], []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        page = self._pages[self._i]
        self._i += 1
        return _Request(page)

    def resolve(self, **kwargs):
        self.resolve_calls.append(kwargs)
        return _Request({})


class _DriveWithProposals:
    def __init__(self, stub): self._stub = stub
    def accessproposals(self): return self._stub


class _ServicesWithProposals:
    def __init__(self, stub): self.drive = _DriveWithProposals(stub)


def test_list_access_proposals_follows_pagination():
    """A file with more pending requests than one page is exactly the file somebody needs the
    tool for. Stopping at page one would report a SHORTER queue than exists, which reads as
    "everyone has been dealt with"."""
    stub = _ProposalsStub([
        {"accessProposals": [{"proposalId": "a"}], "nextPageToken": "n1"},
        {"accessProposals": [{"proposalId": "b"}]},
    ])
    out = ApiBackend(_ServicesWithProposals(stub)).list_access_proposals("f")

    assert [p["proposalId"] for p in out] == ["a", "b"]
    assert len(stub.list_calls) == 2
    assert stub.list_calls[0]["fileId"] == "f"
    assert "pageToken" not in stub.list_calls[0]
    assert stub.list_calls[1]["pageToken"] == "n1"


def test_an_empty_page_is_an_empty_list_not_a_crash():
    """Drive omits `accessProposals` entirely when nothing is pending, and "nobody has asked"
    is the common case rather than an edge one."""
    stub = _ProposalsStub([{}])
    assert ApiBackend(_ServicesWithProposals(stub)).list_access_proposals("f") == []


def test_resolve_sends_the_action_and_the_role_google_expects():
    """The field names are Google's, not ours: `action`, `role` (a LIST, despite granting one
    role), `sendNotification`. A wrong name here is a 400 from Google that `FakeBackend` will
    never produce, on the one call that hands out access."""
    stub = _ProposalsStub([{}])
    ApiBackend(_ServicesWithProposals(stub)).resolve_access_proposal(
        "f", "ap1", action="ACCEPT", roles=["writer"], notify=True)

    call = stub.resolve_calls[0]
    assert call["fileId"] == "f" and call["proposalId"] == "ap1"
    assert call["body"] == {"action": "ACCEPT", "sendNotification": True, "role": ["writer"]}


def test_a_denial_sends_no_role_at_all():
    """A DENY carrying a role would be contradictory - naming an access level while refusing
    access - and it is the kind of thing an API accepts today and rejects later."""
    stub = _ProposalsStub([{}])
    ApiBackend(_ServicesWithProposals(stub)).resolve_access_proposal(
        "f", "ap1", action="DENY", notify=False)

    assert stub.resolve_calls[0]["body"] == {"action": "DENY", "sendNotification": False}


# --- labels: two APIs, and the parameter names differ from everything else here -------


class _LabelsFilesStub:
    def __init__(self, pages):
        self._pages, self._i = pages, 0
        self.calls = []

    def listLabels(self, **kwargs):        # noqa: N802 - Google's method name
        self.calls.append(kwargs)
        page = self._pages[self._i]
        self._i += 1
        return _Request(page)


class _LabelDefsStub:
    def __init__(self, result=None):
        self.calls = []
        self._result = result or {}

    def get(self, **kwargs):
        self.calls.append(kwargs)
        return _Request(self._result)


class _DriveForLabels:
    def __init__(self, files): self._files = files
    def files(self): return self._files


class _ServicesForLabels:
    def __init__(self, files=None, defs=None):
        self.drive = _DriveForLabels(files)
        self._defs = defs

    @property
    def drivelabels(self):
        outer = self
        class _DL:
            def labels(self): return outer._defs
        return _DL()


def test_list_file_labels_paginates_with_maxResults_not_pageSize():
    """This endpoint spells its page size `maxResults`, unlike every other list in this backend,
    which uses `pageSize`. Sending `pageSize` is not an error - Google ignores it - so the call
    silently falls back to the default page size and a heavily-labelled file loses labels with
    no failure anywhere."""
    files = _LabelsFilesStub([
        {"labels": [{"id": "L1"}], "nextPageToken": "n1"},
        {"labels": [{"id": "L2"}]},
    ])
    out = ApiBackend(_ServicesForLabels(files=files)).list_file_labels("f")

    assert [x["id"] for x in out] == ["L1", "L2"]
    assert files.calls[0]["maxResults"] == 100
    assert "pageSize" not in files.calls[0], "wrong parameter name; Google would ignore it"
    assert "pageToken" not in files.calls[0]
    assert files.calls[1]["pageToken"] == "n1"


def test_a_file_with_no_labels_is_an_empty_list():
    files = _LabelsFilesStub([{}])
    assert ApiBackend(_ServicesForLabels(files=files)).list_file_labels("f") == []


def test_get_label_definition_asks_the_full_view():
    """`LABEL_VIEW_BASIC` omits `fields`, so without FULL the response cannot name a field or
    resolve a selection choice - which is most of the reason for calling the second API at all.
    The failure is quiet: a well-formed response that simply has no names in it."""
    defs = _LabelDefsStub({"id": "L1"})
    ApiBackend(_ServicesForLabels(defs=defs)).get_label_definition("L1")

    assert defs.calls[0]["view"] == "LABEL_VIEW_FULL"


def test_the_label_id_is_turned_into_a_resource_name():
    """The Drive Labels API addresses labels as `labels/{id}`, while Drive v3 hands back a bare
    id. Passing the bare id through is a 404 on a label that exists."""
    defs = _LabelDefsStub()
    ApiBackend(_ServicesForLabels(defs=defs)).get_label_definition("L1")
    assert defs.calls[0]["name"] == "labels/L1"


def test_an_already_qualified_name_is_not_doubled():
    """Idempotent, because a caller holding a resource name is the likelier mistake than one
    holding a bare id, and `labels/labels/L1` is a 404 that reads like a missing label."""
    defs = _LabelDefsStub()
    ApiBackend(_ServicesForLabels(defs=defs)).get_label_definition("labels/L1")
    assert defs.calls[0]["name"] == "labels/L1"


def test_get_file_metadata_asks_for_trashed():
    """Dead-entry detection depends on it, and its absence fails SILENTLY.

    A trashed file still resolves by id - `files.get` returns 200 - so without `trashed` in the
    mask the response looks exactly like a live file, and an allowlist entry that has quietly
    stopped covering anything reports as `ok`. `FakeBackend` cannot catch this: it never sees a
    fields mask.
    """
    class _Files:
        def __init__(self): self.calls = []
        def get(self, **kw):
            self.calls.append(kw)
            return _Request({})

    class _D:
        def __init__(self, f): self._f = f
        def files(self): return self._f

    class _S:
        def __init__(self, f): self.drive = _D(f)

    files = _Files()
    ApiBackend(_S(files)).get_file_metadata("f")
    assert "trashed" in files.calls[0]["fields"], (
        "without this, a trashed file is indistinguishable from a live one")


def test_get_document_asks_for_tabs_content():
    """Without `includeTabsContent`, `documents.get` returns THE FIRST TAB ONLY.

    Measured against live Google (`experiments/docs-tabs/`): a two-tab document came back with no
    `tabs` key and only tab 1's text in `body`. `FakeBackend` cannot catch this - it never sees a
    request - so the assertion belongs here.

    Note this parameter and `_content.doc_tab_bodies` are ONE change: with the flag, top-level
    `body` arrives EMPTY and content moves under `tabs[]`. Adding the flag alone would turn a
    truncation into a blank; removing it alone brings the truncation back.
    """
    class _Docs:
        def __init__(self): self.calls = []
        def get(self, **kw):
            self.calls.append(kw)
            return _Request({})

    class _S:
        def __init__(self, d): self.docs = type("D", (), {"documents": lambda s: d})()

    docs = _Docs()
    ApiBackend(_S(docs)).get_document("f")
    assert docs.calls[0].get("includeTabsContent") is True, (
        "without this, a multi-tab document silently reads back as a one-tab document")


def test_get_document_still_passes_the_suggestions_view_mode():
    """The tabs flag must not have displaced the existing parameter - `list_suggestions` depends
    on it, and the two are independent."""
    class _Docs:
        def __init__(self): self.calls = []
        def get(self, **kw):
            self.calls.append(kw)
            return _Request({})

    class _S:
        def __init__(self, d): self.docs = type("D", (), {"documents": lambda s: d})()

    docs = _Docs()
    ApiBackend(_S(docs)).get_document("f", "SUGGESTIONS_INLINE")
    assert docs.calls[0]["suggestionsViewMode"] == "SUGGESTIONS_INLINE"
    assert docs.calls[0]["includeTabsContent"] is True


class TestWriteMasksOmitFieldsDriveRefusesOnWrite:
    """Drive accepts `mentionedEmailAddresses` / `assigneeEmailAddress` on READ and refuses
    them on WRITE. Measured 2026-09-05 against the live API, all six endpoints:

        comments.list  accepted     comments.create  REFUSED
        comments.get   accepted     comments.update  REFUSED
        replies.list   accepted     replies.create   REFUSED
                                    replies.update   REFUSED

    Asking for one in a write's response mask is a hard
    `400 Invalid field selection mentioned_email_addresses`. v0.47.0 (#398) added both to the
    shared masks, which broke create_comment, update_comment, create_reply and update_reply —
    every comment write — for five releases.

    Nothing caught it because `FakeBackend` does not validate field masks, so the entire unit
    suite exercised a double that accepts anything. That is invariant 4's blind spot exactly,
    and this class is the guard for it.
    """

    def test_the_read_masks_still_request_both_fields(self):
        # The other half of the bargain: if these ever fall out of the READ masks, structured
        # @mentions and assignments silently read as absent, which is the bug #398 fixed.
        for mask in (ApiBackend._CF, ApiBackend._RF):
            for name in ApiBackend._WRITE_REFUSED:
                assert f"{name}," in mask or mask.endswith(name), f"{name} missing from a read mask"

    def test_write_masks_contain_neither_refused_field(self):
        for read_mask in (ApiBackend._CF, ApiBackend._RF):
            written = ApiBackend._write_mask(read_mask)
            for name in ApiBackend._WRITE_REFUSED:
                # Not a substring test: `assigneeEmailAddress` is legal INSIDE `replies(...)`,
                # so the check has to be against the top-level field list. Splitting on a bare
                # comma would also fail on the nested `author(...)`, which is why the depth
                # walk exists in the first place.
                top = _top_level_fields(written)
                assert name not in top, f"{name} survived into a write mask: {written}"

    def test_write_mask_keeps_everything_else(self):
        kept = _top_level_fields(ApiBackend._write_mask(ApiBackend._CF))
        for expected in ("id", "anchor", "content", "resolved", "quotedFileContent"):
            assert expected in kept
        # And it must not damage the nested spec, which a naive string replace would.
        assert "replies(" in ApiBackend._write_mask(ApiBackend._CF)

    def test_the_strip_reaches_NESTED_occurrences_too(self):
        """The refusal is by NAME, not by position — measured 2026-09-05.

        `fields=id,replies(mentionedEmailAddresses)` on `comments.create` is refused exactly
        as the top-level form is. The first version of `_write_mask` stripped only the top
        level, on the assumption that a nested occurrence could not matter to a write whose
        response carries no replies. Live Google rejected it on the first call.
        """
        written = ApiBackend._write_mask(ApiBackend._CF)
        for name in ApiBackend._WRITE_REFUSED:
            assert name not in written, f"{name} survived anywhere in {written}"

    def test_a_spec_emptied_by_the_strip_is_dropped_entirely(self):
        # `replies(mentionedEmailAddresses)` must not become the syntactically invalid
        # `replies()`, which Drive would refuse for a different reason and confuse the next
        # person to read the error.
        assert ApiBackend._write_mask("id,replies(mentionedEmailAddresses)") == "id"
        assert ApiBackend._write_mask("id,replies(id,assigneeEmailAddress)") == "id,replies(id)"

    def test_every_write_call_site_uses_the_derived_mask(self):
        """A new write method that reaches for the raw read mask reintroduces the bug."""
        import inspect
        src = inspect.getsource(ApiBackend)
        for method in ("def create_comment", "def create_reply",
                       "def update_comment", "def update_reply"):
            start = src.index(method)
            body = src[start:start + 600]
            assert "_write_mask(" in body, f"{method} does not use the derived write mask"
            assert "fields=self._CF)" not in body and "fields=self._RF)" not in body, \
                f"{method} passes a raw READ mask to a write"


def _top_level_fields(mask: str) -> set[str]:
    depth, out, field = 0, [], []
    for ch in mask:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(field)); field = []
        else:
            field.append(ch)
    out.append("".join(field))
    return {f.split("(")[0] for f in out}


# --- get_about_user: the `.execute` wiring, and the required field mask --------
#
# `FakeBackend` cannot see either of these. It has no request objects, so it cannot notice that
# `_errors.call` is handed a request instead of the unbound `.execute` it is meant to invoke -
# which raises `TypeError: 'HttpRequest' object is not callable` against the real API while
# every fake-backed test stays green. That is how it shipped in the first draft here, and a live
# probe rather than the suite is what caught it.
#
# `_Request` below is deliberately NOT callable, so the wrong wiring fails the same way in a
# test that it does against Google.

class _About:
    def __init__(self, result):
        self._result = result
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(kwargs)
        return _Request(self._result)


class _DriveWithAbout:
    def __init__(self, about):
        self._about = about

    def about(self):
        return self._about


class _ServicesWithAbout:
    def __init__(self, about):
        self.drive = _DriveWithAbout(about)


def test_get_about_user_executes_the_request_rather_than_passing_it():
    about = _About({"user": {"emailAddress": "a@b.c", "displayName": "A B"}})
    backend = ApiBackend(_ServicesWithAbout(about))

    assert backend.get_about_user() == {"emailAddress": "a@b.c", "displayName": "A B"}


def test_get_about_user_asks_for_the_field_mask_about_get_requires():
    """`about.get` returns 400 without `fields`, so the mask is load-bearing, not an
    optimisation. It is also narrow on purpose: the resource carries storage quota and a long
    tail of account settings that answering "who am I" has no business reading."""
    about = _About({"user": {}})
    ApiBackend(_ServicesWithAbout(about)).get_about_user()

    assert about.calls == [{"fields": "user(emailAddress,displayName)"}]


def test_a_response_without_a_user_node_is_an_empty_dict_not_none():
    """Unknown must arrive as something a caller can `.get` on. `None` here would turn an odd
    account into an AttributeError two layers up."""
    backend = ApiBackend(_ServicesWithAbout(_About({})))
    assert backend.get_about_user() == {}


# --- the other half of the census: every READ reaches the error translator -----------------
#
# `WRITE_CALLS` above exists because a write that skips `_errors.call` silently gains a retry
# that can double-apply. Reads have the mirror-image problem and it is not smaller: a read that
# skips `_errors.call` lets a raw `googleapiclient.errors.HttpError` escape into the MCP layer,
# where it arrives as a traceback rather than as "that file is not shared with this account" or
# "the Drive API is not enabled on this project, here is the link to enable it".
#
# Every typed exception this library raises about Drive is produced in `_errors.call`. A method
# that does not go through it produces none of them.

READ_CALLS = {
    "get_about_user":          lambda b: b.get_about_user(),
    "get_file_metadata":       lambda b: b.get_file_metadata("f"),
    "get_drive":               lambda b: b.get_drive("d"),
    "search_files":            lambda b: b.search_files("name contains 'x'"),
    "list_comments":           lambda b: b.list_comments("f"),
    "get_comment":             lambda b: b.get_comment("f", "c"),
    "list_permissions":        lambda b: b.list_permissions("f"),
    "list_access_proposals":   lambda b: b.list_access_proposals("f"),
    "list_file_labels":        lambda b: b.list_file_labels("f"),
    "get_label_definition":    lambda b: b.get_label_definition("l"),
    "get_document":            lambda b: b.get_document("f"),
    "get_spreadsheet":         lambda b: b.get_spreadsheet("f"),
    "get_presentation":        lambda b: b.get_presentation("f"),
    "get_values":              lambda b: b.get_values("f", "A1:B2"),
    "get_sheet_notes":         lambda b: b.get_sheet_notes("f"),
    "export_file":             lambda b: b.export_file("f", "text/plain"),
    "download_file":           lambda b: b.download_file("f"),
}

# `copy_file` belongs to neither list, and finding that out is the point of the census.
#
# It CREATES a Drive file, so it is non-idempotent for the same reason every write is: a
# retried 5xx that had already landed leaves two copies. But it is not in `WRITE_CALLS`,
# because that set is derived from `access == MODIFY` and `copy_file`'s gate is
# `Gate(capability="file.create", access="read", file_scoped=True)` - the file it is
# CHECKED against is the source, which it only reads.
#
# That asymmetry with `create_file` (`access="modify"`, `file_scoped=False`) is deliberate as
# far as the allowlist goes, and it is noted in #491 for the security-audit pass rather than
# changed here: under READ=* with a narrow MODIFY list, `copy_file` can duplicate any readable
# file, which is a creation the modify allowlist does not bound.
CREATES_WITHOUT_A_MODIFY_GATE = {
    "copy_file": lambda b: b.copy_file("f"),
}


def _public_methods() -> set[str]:
    import inspect

    return {name for name, _ in inspect.getmembers(ApiBackend, inspect.isfunction)
            if not name.startswith("_")}


def test_every_public_backend_method_is_accounted_for():
    """Derived, like the write census, and for the same reason: a method added to `ApiBackend`
    and to no list here is a method nobody tests, and nothing says so. Adding one must be a
    deliberate act of putting it in a list."""
    known = (set(WRITE_CALLS) | set(READ_CALLS) | set(CREATES_WITHOUT_A_MODIFY_GATE)
             | set(NOT_IMPLEMENTED_SO_NO_REQUEST))
    unaccounted = sorted(_public_methods() - known)
    assert unaccounted == [], (
        f"these ApiBackend methods appear in no census: {unaccounted}. Add each to "
        f"WRITE_CALLS or READ_CALLS - an untested backend method reaches Google untranslated.")

    stale = sorted(known - _public_methods() - set(NOT_IMPLEMENTED_SO_NO_REQUEST))
    assert stale == [], f"these census entries name methods that no longer exist: {stale}"


def test_every_read_goes_through_the_error_translator(monkeypatch):
    """The mirror of `test_all_writes_are_non_idempotent`. Every typed exception this library
    raises about Drive - NotFoundError, AccessError, the "enable the API" message with its
    activation URL - is produced inside `_errors.call`. A read that bypasses it hands the MCP
    layer a raw HttpError, which surfaces as a traceback and tells the user nothing."""
    reached: set[str] = set()
    current = [""]

    def fake_call(fn, *args, idempotent=True, _sleep=None, **kwargs):
        reached.add(current[0])
        return {}

    monkeypatch.setattr("csa_google_workspace.backend._errors.call", fake_call)
    b = ApiBackend(_Chain())
    for name, call in sorted({**READ_CALLS, **CREATES_WITHOUT_A_MODIFY_GATE}.items()):
        current[0] = name
        call(b)

    missed = sorted((set(READ_CALLS) | set(CREATES_WITHOUT_A_MODIFY_GATE)) - reached)
    assert missed == [], (
        f"these reads never reached _errors.call: {missed}. Each returns a raw HttpError to "
        f"the caller instead of a typed, actionable one.")


def test_reads_keep_their_retry(monkeypatch):
    """The other mirror. `idempotent=False` costs a call its 5xx retry, correctly for a write -
    the mutation may already have landed - and pointlessly for a read, where retrying a
    transient 503 is exactly the right thing and a copy-pasted flag would quietly stop it."""
    flags: dict[str, bool] = {}
    current = [""]

    def fake_call(fn, *args, idempotent=True, _sleep=None, **kwargs):
        flags[current[0]] = idempotent
        return {}

    monkeypatch.setattr("csa_google_workspace.backend._errors.call", fake_call)
    b = ApiBackend(_Chain())
    for name, call in sorted(READ_CALLS.items()):
        current[0] = name
        call(b)

    wrong = sorted(n for n, flag in flags.items() if flag is False)
    assert wrong == [], (
        f"these reads were marked non-idempotent: {wrong}. A read is safe to retry, and the "
        f"flag costs it the 5xx retry it should have.")


def test_copy_is_non_idempotent_even_though_it_is_not_modify_gated(monkeypatch):
    """The gate answers "which allowlist applies"; the flag answers "is this safe to retry".
    They are different questions and `copy_file` is where they diverge - it is checked against
    the source file it reads, and it creates a new one. A retried 5xx that had already landed
    leaves the person with two copies and no way to tell which run made which."""
    seen = {}

    def fake_call(fn, *args, idempotent=True, _sleep=None, **kwargs):
        seen["idempotent"] = idempotent
        return {}

    monkeypatch.setattr("csa_google_workspace.backend._errors.call", fake_call)
    CREATES_WITHOUT_A_MODIFY_GATE["copy_file"](ApiBackend(_Chain()))

    assert seen["idempotent"] is False


# --- the field-mask strip, at depth -------------------------------------------------------
#
# Drive accepts `mentionedEmailAddresses` and `assigneeEmailAddress` on a READ and refuses them
# on a WRITE's response mask, for comments and replies alike (measured 2026-09-05). Asking for
# one is a hard `400 Invalid field selection`, which is how v0.47.0 broke every comment write in
# this library for five releases - FakeBackend does not validate masks, so the whole unit suite
# was exercising a double that accepts anything.
#
# The strip is BY NAME AND AT EVERY DEPTH. The first version stripped only the top level, on the
# assumption that a nested one could not matter, and live Google rejected it immediately.

class TestTheWriteMask:
    def test_a_refused_field_is_stripped_at_the_top_level(self):
        assert ApiBackend._write_mask("id,mentionedEmailAddresses,content") == "id,content"

    def test_a_refused_field_is_stripped_inside_a_nested_spec(self):
        """The half live Google caught. `replies(mentionedEmailAddresses)` is refused exactly
        as the bare form is, because the refusal is by name rather than by position."""
        got = ApiBackend._write_mask("id,replies(id,mentionedEmailAddresses,content)")
        assert got == "id,replies(id,content)"

    def test_a_spec_emptied_by_the_strip_is_dropped_entirely(self):
        """`replies()` is not valid syntax. A spec whose every field was refused has to
        disappear, not become an empty pair of brackets."""
        assert ApiBackend._write_mask("id,replies(mentionedEmailAddresses)") == "id"

    def test_a_whole_spec_named_after_a_refused_field_is_dropped_with_its_contents(self):
        """The branch where the REFUSED NAME is the one carrying the brackets. Keeping its
        inner fields would ask for the refused thing under a different shape."""
        got = ApiBackend._write_mask("id,assigneeEmailAddress(displayName),content")
        assert got == "id,content"

    def test_nesting_deeper_than_one_level_is_stripped_too(self):
        got = ApiBackend._write_mask("a(b(c,assigneeEmailAddress),d)")
        assert got == "a(b(c),d)"

    def test_an_unbalanced_mask_does_not_hang_or_raise(self):
        """Not a mask this library builds - the constants are literals - but the parser scans
        to the end looking for a closing bracket that is not there. It has to terminate and
        return something, because a crash inside mask construction would break every write
        with a traceback that names none of them."""
        assert isinstance(ApiBackend._write_mask("id,replies(content"), str)

    def test_the_real_masks_come_through_with_the_two_fields_gone(self):
        """The derivation this exists for, against the constants actually used."""
        for mask in (ApiBackend._CF, ApiBackend._RF):
            stripped = ApiBackend._write_mask(mask)
            for refused in ApiBackend._WRITE_REFUSED:
                assert refused not in stripped
            assert "id" in stripped, "the strip took the whole mask"

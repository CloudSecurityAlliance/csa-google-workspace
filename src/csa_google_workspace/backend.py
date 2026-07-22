"""Backend seam. ApiBackend uses the real Google APIs; FakeBackend is in-memory for tests.
Operations Google exposes only through the UI raise UnsupportedOperation on ApiBackend; a
future PlaywrightBackend could implement them without changing the public API."""
import copy
from typing import Protocol

from . import _errors
from . import exceptions as exc


class Backend(Protocol):
    def get_file_metadata(self, file_id: str) -> dict: ...
    def accept_suggestion(self, file_id: str, suggestion_id: str) -> None: ...
    def create_cell_anchored_comment(self, file_id: str, cell: str, text: str) -> None: ...
    def list_comments(self, file_id: str, include_deleted: bool = False,
                      start_modified_time: str | None = None) -> list[dict]: ...
    def get_comment(self, file_id: str, comment_id: str) -> dict: ...
    def create_comment(self, file_id: str, content: str) -> dict: ...
    def create_reply(self, file_id: str, comment_id: str,
                     content: str | None = None, action: str | None = None) -> dict: ...
    def update_comment(self, file_id: str, comment_id: str, content: str) -> dict: ...
    def update_reply(self, file_id: str, comment_id: str, reply_id: str, content: str) -> dict: ...
    def delete_comment(self, file_id: str, comment_id: str) -> None: ...
    def delete_reply(self, file_id: str, comment_id: str, reply_id: str) -> None: ...
    def export_file(self, file_id: str, mime_type: str) -> bytes: ...
    def get_document(self, file_id: str, suggestions_view_mode: str | None = None) -> dict: ...
    def get_spreadsheet(self, file_id: str) -> dict: ...
    def get_values(self, file_id: str, a1_range: str) -> list: ...
    def get_presentation(self, file_id: str) -> dict: ...
    def docs_batch_update(self, file_id: str, requests: list) -> dict: ...
    def sheets_values_update(self, file_id: str, a1_range: str, values: list,
                             value_input_option: str = "RAW") -> dict: ...
    def sheets_values_append(self, file_id: str, a1_range: str, values: list,
                             value_input_option: str = "RAW") -> dict: ...
    def sheets_values_clear(self, file_id: str, a1_range: str) -> dict: ...
    def sheets_batch_update(self, file_id: str, requests: list) -> dict: ...
    def slides_batch_update(self, file_id: str, requests: list) -> dict: ...


class FakeBackend:
    """In-memory backend for unit tests. `files` maps file_id -> metadata dict."""

    def __init__(self, files, *, documents=None, spreadsheets=None,
                 values=None, presentations=None, exports=None):
        self._files = files
        self._comments = {}
        self._seq = 0
        self._documents = documents or {}
        self._spreadsheets = spreadsheets or {}
        self._values = values or {}
        self._presentations = presentations or {}
        self._exports = exports or {}
        self._writes = []

    def get_file_metadata(self, file_id: str) -> dict:
        try:
            return self._files[file_id]
        except KeyError:
            raise exc.NotFoundError(f"file '{file_id}' not found") from None

    def accept_suggestion(self, file_id: str, suggestion_id: str) -> None:
        raise exc.UnsupportedOperation("accept_suggestion is not supported by FakeBackend")

    def create_cell_anchored_comment(self, file_id: str, cell: str, text: str) -> None:
        raise exc.UnsupportedOperation("cell-anchored comments are not creatable")

    def _new_id(self, prefix):
        self._seq += 1
        return f"{prefix}{self._seq}"

    def _require(self, file_id, comment_id):
        c = self._comments.get((file_id, comment_id))
        if c is None:
            raise exc.NotFoundError(f"comment '{comment_id}' not found")
        return c

    def list_comments(self, file_id, include_deleted=False, start_modified_time=None):
        out = [c for (f, _), c in self._comments.items() if f == file_id]
        if not include_deleted:
            out = [c for c in out if not c.get("deleted")]
        if start_modified_time:
            out = [c for c in out if c.get("modifiedTime", "") >= start_modified_time]
        return [copy.deepcopy(c) for c in out]

    def get_comment(self, file_id, comment_id):
        return copy.deepcopy(self._require(file_id, comment_id))

    def create_comment(self, file_id, content):
        self.get_file_metadata(file_id)  # validates the file exists (raises NotFoundError)
        cid = self._new_id("c")
        c = {"id": cid, "content": content, "htmlContent": content, "deleted": False,
             "author": {"displayName": "Test User", "me": True},
             "createdTime": "2026-01-01T00:00:00Z", "modifiedTime": "2026-01-01T00:00:00Z",
             "replies": []}
        self._comments[(file_id, cid)] = c
        return copy.deepcopy(c)

    def create_reply(self, file_id, comment_id, content=None, action=None):
        c = self._require(file_id, comment_id)
        rid = self._new_id("r")
        r = {"id": rid, "content": content or "", "htmlContent": content or "",
             "deleted": False, "author": {"displayName": "Test User", "me": True},
             "createdTime": "2026-01-01T00:00:00Z"}
        if action:
            r["action"] = action
            c["resolved"] = (action == "resolve")   # flip parent (MEASURED)
        c["replies"].append(r)
        return copy.deepcopy(r)

    def update_comment(self, file_id, comment_id, content):
        c = self._require(file_id, comment_id)
        c["content"] = content; c["htmlContent"] = content
        return copy.deepcopy(c)

    def update_reply(self, file_id, comment_id, reply_id, content):
        c = self._require(file_id, comment_id)
        for r in c["replies"]:
            if r["id"] == reply_id:
                r["content"] = content; r["htmlContent"] = content
                return copy.deepcopy(r)
        raise exc.NotFoundError(f"reply '{reply_id}' not found")

    def delete_comment(self, file_id, comment_id):
        c = self._require(file_id, comment_id)
        c["deleted"] = True
        c.pop("content", None); c.pop("htmlContent", None); c.pop("author", None)  # strip (MEASURED)
        for r in c["replies"]:
            r["deleted"] = True
            r.pop("content", None); r.pop("htmlContent", None); r.pop("author", None)

    def delete_reply(self, file_id, comment_id, reply_id):
        c = self._require(file_id, comment_id)
        for r in c["replies"]:
            if r["id"] == reply_id:
                r["deleted"] = True
                r.pop("content", None); r.pop("htmlContent", None); r.pop("author", None)
                return
        raise exc.NotFoundError(f"reply '{reply_id}' not found")

    def _fixture(self, store, key, kind):
        if key not in store:
            raise exc.NotFoundError(f"{kind} '{key}' not found")
        return copy.deepcopy(store[key])

    def export_file(self, file_id, mime_type):
        return self._fixture(self._exports, (file_id, mime_type), "export")

    def get_document(self, file_id, suggestions_view_mode=None):
        key = (file_id, suggestions_view_mode)
        if key in self._documents:
            return copy.deepcopy(self._documents[key])
        return self._fixture(self._documents, file_id, "document")

    def get_spreadsheet(self, file_id):
        return self._fixture(self._spreadsheets, file_id, "spreadsheet")

    def get_values(self, file_id, a1_range):
        return copy.deepcopy(self._values.get((file_id, a1_range), []))

    def get_presentation(self, file_id):
        return self._fixture(self._presentations, file_id, "presentation")

    def docs_batch_update(self, file_id, requests):
        self._writes.append((file_id, "docs", requests))
        return {}

    def sheets_values_update(self, file_id, a1_range, values, value_input_option="RAW"):
        self._writes.append((file_id, "sheets_values_update", a1_range, values, value_input_option))
        self._values[(file_id, a1_range)] = values
        return {}

    def sheets_values_append(self, file_id, a1_range, values, value_input_option="RAW"):
        self._writes.append((file_id, "sheets_values_append", a1_range, values, value_input_option))
        self._values[(file_id, a1_range)] = self._values.get((file_id, a1_range), []) + values
        return {}

    def sheets_values_clear(self, file_id, a1_range):
        self._writes.append((file_id, "sheets_values_clear", a1_range))
        self._values.pop((file_id, a1_range), None)
        return {}

    def sheets_batch_update(self, file_id, requests):
        self._writes.append((file_id, "sheets", requests))
        return {}

    def slides_batch_update(self, file_id, requests):
        self._writes.append((file_id, "slides", requests))
        return {}


class ApiBackend:
    """Real backend over google-api-python-client. `services` is a ServiceRegistry (Task 4)."""

    def __init__(self, services):
        self._services = services

    def get_file_metadata(self, file_id: str) -> dict:
        return _errors.call(self._services.drive.files()
                            .get(fileId=file_id, fields="id,name,mimeType,webViewLink",
                                 supportsAllDrives=True).execute)

    def accept_suggestion(self, file_id: str, suggestion_id: str) -> None:
        raise exc.UnsupportedOperation(
            "The Google Docs API has no accept/reject-suggestion endpoint "
            "(verified by probe). A PlaywrightBackend is required."
        )

    def create_cell_anchored_comment(self, file_id: str, cell: str, text: str) -> None:
        raise exc.UnsupportedOperation(
            "Cell-anchored comments cannot be created via the API; use a file-level "
            "comment with a #range deep-link instead."
        )

    _CF = "id,anchor,content,htmlContent,resolved,deleted,createdTime,modifiedTime," \
          "author(displayName,emailAddress,me,photoLink),quotedFileContent," \
          "replies(id,content,htmlContent,action,deleted,createdTime,modifiedTime," \
          "author(displayName,emailAddress,me,photoLink))"
    _RF = "id,content,htmlContent,action,deleted,createdTime,modifiedTime," \
          "author(displayName,emailAddress,me,photoLink)"

    def _comments(self):
        return self._services.drive.comments()

    def list_comments(self, file_id, include_deleted=False, start_modified_time=None):
        out, page = [], None
        while True:
            kw = {"fileId": file_id, "includeDeleted": include_deleted,
                  "fields": f"comments({self._CF}),nextPageToken", "pageSize": 100}
            if start_modified_time:
                kw["startModifiedTime"] = start_modified_time
            if page:
                kw["pageToken"] = page
            resp = _errors.call(self._comments().list(**kw).execute)
            out.extend(resp.get("comments", []))
            page = resp.get("nextPageToken")
            if not page:
                return out

    def get_comment(self, file_id, comment_id):
        return _errors.call(self._comments().get(
            fileId=file_id, commentId=comment_id, fields=self._CF).execute)

    def create_comment(self, file_id, content):
        return _errors.call(self._comments().create(
            fileId=file_id, body={"content": content}, fields=self._CF).execute,
            idempotent=False)

    def create_reply(self, file_id, comment_id, content=None, action=None):
        body = {}
        if content is not None:
            body["content"] = content
        if action:
            body["action"] = action
        return _errors.call(self._services.drive.replies().create(
            fileId=file_id, commentId=comment_id, body=body, fields=self._RF).execute,
            idempotent=False)

    def update_comment(self, file_id, comment_id, content):
        return _errors.call(self._comments().update(
            fileId=file_id, commentId=comment_id, body={"content": content}, fields=self._CF).execute,
            idempotent=False)

    def update_reply(self, file_id, comment_id, reply_id, content):
        return _errors.call(self._services.drive.replies().update(
            fileId=file_id, commentId=comment_id, replyId=reply_id,
            body={"content": content}, fields=self._RF).execute,
            idempotent=False)

    def delete_comment(self, file_id, comment_id):
        _errors.call(self._comments().delete(fileId=file_id, commentId=comment_id).execute,
                     idempotent=False)

    def delete_reply(self, file_id, comment_id, reply_id):
        _errors.call(self._services.drive.replies().delete(
            fileId=file_id, commentId=comment_id, replyId=reply_id).execute,
            idempotent=False)

    def export_file(self, file_id, mime_type):
        return _errors.call(self._services.drive.files()
                            .export(fileId=file_id, mimeType=mime_type).execute)

    def get_document(self, file_id, suggestions_view_mode=None):
        kw = {"documentId": file_id}
        if suggestions_view_mode:
            kw["suggestionsViewMode"] = suggestions_view_mode
        return _errors.call(self._services.docs.documents().get(**kw).execute)

    def get_spreadsheet(self, file_id):
        return _errors.call(self._services.sheets.spreadsheets()
                            .get(spreadsheetId=file_id,
                                 fields="sheets(properties(sheetId,title))").execute)

    def get_values(self, file_id, a1_range):
        resp = _errors.call(self._services.sheets.spreadsheets().values()
                            .get(spreadsheetId=file_id, range=a1_range).execute)
        return resp.get("values", [])

    def get_presentation(self, file_id):
        return _errors.call(self._services.slides.presentations().get(presentationId=file_id).execute)

    def docs_batch_update(self, file_id, requests):
        return _errors.call(self._services.docs.documents().batchUpdate(
            documentId=file_id, body={"requests": requests}).execute,
            idempotent=False)

    def sheets_values_update(self, file_id, a1_range, values, value_input_option="RAW"):
        return _errors.call(self._services.sheets.spreadsheets().values().update(
            spreadsheetId=file_id, range=a1_range, valueInputOption=value_input_option,
            body={"values": values}).execute,
            idempotent=False)

    def sheets_values_append(self, file_id, a1_range, values, value_input_option="RAW"):
        # append is NOT idempotent: a retried request would add the rows twice. Never retry on 5xx.
        return _errors.call(self._services.sheets.spreadsheets().values().append(
            spreadsheetId=file_id, range=a1_range, valueInputOption=value_input_option,
            insertDataOption="INSERT_ROWS", body={"values": values}).execute,
            idempotent=False)

    def sheets_values_clear(self, file_id, a1_range):
        return _errors.call(self._services.sheets.spreadsheets().values().clear(
            spreadsheetId=file_id, range=a1_range, body={}).execute,
            idempotent=False)

    def sheets_batch_update(self, file_id, requests):
        return _errors.call(self._services.sheets.spreadsheets().batchUpdate(
            spreadsheetId=file_id, body={"requests": requests}).execute,
            idempotent=False)

    def slides_batch_update(self, file_id, requests):
        return _errors.call(self._services.slides.presentations().batchUpdate(
            presentationId=file_id, body={"requests": requests}).execute,
            idempotent=False)

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


class FakeBackend:
    """In-memory backend for unit tests. `files` maps file_id -> metadata dict."""

    def __init__(self, files: dict[str, dict]):
        self._files = files
        self._comments: dict[str, dict] = {}
        self._seq = 0

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


class ApiBackend:
    """Real backend over google-api-python-client. `services` is a ServiceRegistry (Task 4)."""

    def __init__(self, services):
        self._services = services

    def get_file_metadata(self, file_id: str) -> dict:
        return (self._services.drive.files()
                .get(fileId=file_id, fields="id,name,mimeType,webViewLink")
                .execute())

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
            fileId=file_id, body={"content": content}, fields=self._CF).execute)

    def create_reply(self, file_id, comment_id, content=None, action=None):
        body = {}
        if content is not None:
            body["content"] = content
        if action:
            body["action"] = action
        return _errors.call(self._services.drive.replies().create(
            fileId=file_id, commentId=comment_id, body=body, fields=self._RF).execute)

    def update_comment(self, file_id, comment_id, content):
        return _errors.call(self._comments().update(
            fileId=file_id, commentId=comment_id, body={"content": content}, fields=self._CF).execute)

    def update_reply(self, file_id, comment_id, reply_id, content):
        return _errors.call(self._services.drive.replies().update(
            fileId=file_id, commentId=comment_id, replyId=reply_id,
            body={"content": content}, fields=self._RF).execute)

    def delete_comment(self, file_id, comment_id):
        _errors.call(self._comments().delete(fileId=file_id, commentId=comment_id).execute)

    def delete_reply(self, file_id, comment_id, reply_id):
        _errors.call(self._services.drive.replies().delete(
            fileId=file_id, commentId=comment_id, replyId=reply_id).execute)

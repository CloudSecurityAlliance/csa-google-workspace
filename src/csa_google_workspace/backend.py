"""Backend seam. ApiBackend uses the real Google APIs; FakeBackend is in-memory for tests.
Operations Google exposes only through the UI raise UnsupportedOperation on ApiBackend; a
future PlaywrightBackend could implement them without changing the public API."""
from typing import Protocol

from . import exceptions as exc


class Backend(Protocol):
    def get_file_metadata(self, file_id: str) -> dict: ...
    def accept_suggestion(self, file_id: str, suggestion_id: str) -> None: ...
    def create_cell_anchored_comment(self, file_id: str, cell: str, text: str) -> None: ...


class FakeBackend:
    """In-memory backend for unit tests. `files` maps file_id -> metadata dict."""

    def __init__(self, files: dict[str, dict]):
        self._files = files

    def get_file_metadata(self, file_id: str) -> dict:
        try:
            return self._files[file_id]
        except KeyError:
            raise exc.NotFoundError(f"file '{file_id}' not found") from None

    def accept_suggestion(self, file_id: str, suggestion_id: str) -> None:
        raise exc.UnsupportedOperation("accept_suggestion is not supported by FakeBackend")

    def create_cell_anchored_comment(self, file_id: str, cell: str, text: str) -> None:
        raise exc.UnsupportedOperation("cell-anchored comments are not creatable")


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

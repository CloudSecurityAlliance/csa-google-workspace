import pytest

from csa_google_workspace import exceptions as exc
from csa_google_workspace.backend import ApiBackend, FakeBackend

FILES = {"doc1": {"id": "doc1", "name": "D", "mimeType": "application/vnd.google-apps.document",
                  "webViewLink": "https://docs.google.com/document/d/doc1/edit"}}


def test_fake_backend_returns_metadata():
    assert FakeBackend(FILES).get_file_metadata("doc1")["mimeType"].endswith("document")


def test_fake_backend_missing_file_raises_not_found():
    with pytest.raises(exc.NotFoundError):
        FakeBackend(FILES).get_file_metadata("nope")


def test_api_backend_accept_suggestion_unsupported():
    with pytest.raises(exc.UnsupportedOperation):
        ApiBackend(services=None).accept_suggestion("doc1", "sug1")


def test_api_backend_cell_anchored_comment_unsupported():
    with pytest.raises(exc.UnsupportedOperation):
        ApiBackend(services=None).create_cell_anchored_comment("sheet1", "B11", "hi")

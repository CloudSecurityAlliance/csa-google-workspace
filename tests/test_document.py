import pytest
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.base import subclass_for_mime, Document
from csa_google_workspace.documents.doc import Doc
from csa_google_workspace.documents.sheet import Sheet
from csa_google_workspace.documents.slides import Slides
from csa_google_workspace import exceptions as exc

DOC_MIME = "application/vnd.google-apps.document"


def test_subclass_for_mime_maps_each_type():
    assert subclass_for_mime(DOC_MIME) is Doc
    assert subclass_for_mime("application/vnd.google-apps.spreadsheet") is Sheet
    assert subclass_for_mime("application/vnd.google-apps.presentation") is Slides


def test_subclass_for_mime_rejects_unknown():
    with pytest.raises(exc.UnsupportedOperation):
        subclass_for_mime("application/pdf")


def test_document_exposes_metadata():
    meta = {"id": "d1", "name": "My Doc", "mimeType": DOC_MIME,
            "webViewLink": "https://docs.google.com/document/d/d1/edit"}
    d = Doc(FakeBackend({}), meta, read_only=False)
    assert (d.id, d.name, d.type, d.read_only) == ("d1", "My Doc", "document", False)
    assert isinstance(d, Document)

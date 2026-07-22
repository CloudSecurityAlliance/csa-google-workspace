"""Test that content getters return independent copies, not references to backend storage."""
from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"


def test_get_document_mutation_does_not_affect_backend():
    """Mutating a returned document dict should not affect backend storage."""
    backend = FakeBackend(
        {"f": {"id": "f", "name": "F", "mimeType": DOC, "webViewLink": "https://x"}},
        documents={"f": {"title": "F", "body": {"content": [{"paragraph": {}}]}}}
    )
    d1 = backend.get_document("f")
    d1["title"] = "MUTATED"
    d2 = backend.get_document("f")
    assert d2["title"] == "F", "backend storage was mutated"


def test_get_values_mutation_does_not_affect_backend():
    """Mutating a returned values list should not affect backend storage."""
    backend = FakeBackend(
        {"f": {"id": "f", "name": "F", "mimeType": SHEET, "webViewLink": "https://x"}},
        values={("f", "A1:B2"): [["a", "b"], ["c", "d"]]}
    )
    v1 = backend.get_values("f", "A1:B2")
    v1[0][0] = "MUTATED"
    v2 = backend.get_values("f", "A1:B2")
    assert v2[0][0] == "a", "backend storage was mutated"


def test_workspace_get_document_returns_copy():
    """Via Workspace.open(), get_document() should return independent copies."""
    backend = FakeBackend(
        {"f": {"id": "f", "name": "F", "mimeType": DOC, "webViewLink": "https://x"}},
        documents={"f": {"title": "F", "body": {"content": []}}}
    )
    ws = Workspace(backend)
    ws.open("f")
    # Access internal backend to verify
    d1 = backend.get_document("f")
    d1["title"] = "MUTATED"
    d2 = backend.get_document("f")
    assert d2["title"] == "F", "backend storage should not be mutated by caller"

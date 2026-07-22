from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
META = {"d": {"id": "d", "name": "D", "mimeType": DOC, "webViewLink": "https://x/document/d/d/edit"}}


def _run(text, ins=None):
    tr = {"textRun": {"content": text}}
    if ins:
        tr["textRun"]["suggestedInsertionIds"] = ins
    return tr


def _para(*runs):
    return {"paragraph": {"elements": list(runs)}}


def _doc_with_modes():
    inline = {"body": {"content": [_para(_run("Base "), _run("added", ins=["s1"]))]}}
    accepted = {"body": {"content": [_para(_run("Base added"))]}}
    rejected = {"body": {"content": [_para(_run("Base "))]}}
    return FakeBackend(META, documents={
        ("d", "SUGGESTIONS_INLINE"): inline,
        ("d", "PREVIEW_SUGGESTIONS_ACCEPTED"): accepted,
        ("d", "PREVIEW_WITHOUT_SUGGESTIONS"): rejected,
        "d": inline,
    })


def test_suggestions_lists_grouped():
    d = Workspace(_doc_with_modes()).open("d")
    s = d.suggestions
    assert len(s) == 1 and s[0].kind == "insertion" and s[0].text == "added"


def test_as_text_accepted_and_rejected_previews():
    d = Workspace(_doc_with_modes()).open("d")
    assert d.as_text(suggestions="accepted") == "Base added"
    assert d.as_text(suggestions="rejected") == "Base "


def test_as_text_default_still_works():
    d = Workspace(_doc_with_modes()).open("d")
    assert "Base" in d.as_text()


def test_as_text_inline_mode():
    d = Workspace(_doc_with_modes()).open("d")
    assert d.as_text(suggestions="inline") == "Base added"

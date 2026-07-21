from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend

PRES = "application/vnd.google-apps.presentation"
META = {"p": {"id": "p", "name": "P", "mimeType": PRES, "webViewLink": "https://x/presentation/d/p/edit"}}


def _shape(text):
    return {"shape": {"text": {"textElements": [{"textRun": {"content": text}}]}}}


PRESENTATION = {"slides": [
    {"pageElements": [_shape("Title slide\n"), _shape("subtitle\n")]},
    {"pageElements": [_shape("Second slide\n")]},
]}


def slides():
    return Workspace(FakeBackend(META, presentations={"p": PRESENTATION})).open("p")


def test_slides_list_and_per_slide_text():
    s = slides().slides
    assert len(s) == 2
    assert "Title slide" in s[0].as_text() and "subtitle" in s[0].as_text()
    assert "Second slide" in s[1].as_text()


def test_deck_as_text_joins_all_slides():
    t = slides().as_text()
    assert "Title slide" in t and "Second slide" in t


def test_slide_notes():
    # Create a presentation with a slide containing speaker notes
    presentation_with_notes = {"slides": [
        {"pageElements": [_shape("Slide with notes\n")],
         "slideProperties": {"notesPage": {"pageElements": [
             {"shape": {"text": {"textElements": [{"textRun": {"content": "speaker note here"}}]}}}
         ]}}}
    ]}
    workspace = Workspace(FakeBackend(META, presentations={"p": presentation_with_notes}))
    slide_deck = workspace.open("p")
    assert "speaker note here" in slide_deck.slides[0].notes

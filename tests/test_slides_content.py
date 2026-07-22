from csa_google_workspace import Workspace, _content
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


def test_slide_shape_ids_lists_text_capable_shapes():
    pres = {"slides": [{"pageElements": [
        {"objectId": "box1", "shape": {"text": {"textElements": []}}},
        {"objectId": "box2", "shape": {}},                      # empty text box still targetable
        {"objectId": "img1", "image": {}},                      # not a shape -> excluded
        {"line": {}},                                            # no objectId -> excluded
    ]}]}
    deck = Workspace(FakeBackend(META, presentations={"p": pres})).open("p")
    assert deck.slides[0].shape_ids == ["box1", "box2"]


def test_slide_text_recurses_into_tables_and_element_groups():
    slide = {"pageElements": [
        _shape("shape text\n"),
        {"table": {"tableRows": [
            {"tableCells": [{"text": {"textElements": [{"textRun": {"content": "cell text"}}]}}]}
        ]}},
        {"elementGroup": {"children": [_shape("grouped text")]}},
    ]}
    text = _content.slide_text(slide)
    assert "shape text" in text
    assert "cell text" in text
    assert "grouped text" in text

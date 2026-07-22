from csa_google_workspace.suggestions import Suggestion, extract_suggestions
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
META = {"d": {"id": "d", "name": "D", "mimeType": DOC, "webViewLink": "https://x/document/d/d/edit"}}


def _run(text, ins=None, dele=None):
    tr = {"textRun": {"content": text}}
    if ins:
        tr["textRun"]["suggestedInsertionIds"] = ins
    if dele:
        tr["textRun"]["suggestedDeletionIds"] = dele
    return tr


def _doc(*runs):
    return {"body": {"content": [{"paragraph": {"elements": list(runs)}}]}}


def test_insertion_spanning_multiple_runs_is_one_suggestion():
    doc = _doc(_run("Hello ", ins=["s1"]), _run("world", ins=["s1"]), _run(" plain"))
    sugg = extract_suggestions(doc)
    assert len(sugg) == 1
    assert sugg[0].suggestion_id == "s1" and sugg[0].kind == "insertion" and sugg[0].text == "Hello world"


def test_deletion_detected():
    sugg = extract_suggestions(_doc(_run("remove me", dele=["s2"])))
    assert sugg[0].kind == "deletion" and sugg[0].text == "remove me"


def test_no_author_field():
    assert not hasattr(extract_suggestions(_doc(_run("x", ins=["s1"])))[0], "author")


def test_get_document_view_mode_fixture_lookup():
    b = FakeBackend(META, documents={("d", "PREVIEW_SUGGESTIONS_ACCEPTED"): {"body": {"content": []}, "title": "accepted"}})
    assert b.get_document("d", "PREVIEW_SUGGESTIONS_ACCEPTED")["title"] == "accepted"


def test_get_document_falls_back_to_plain_key():
    b = FakeBackend(META, documents={"d": {"title": "plain"}})
    assert b.get_document("d")["title"] == "plain"                    # existing single-arg behavior intact
    assert b.get_document("d", "SUGGESTIONS_INLINE")["title"] == "plain"  # falls back to plain key


def test_suggestion_inside_table_cell_is_found():
    doc = {"body": {"content": [
        {"table": {"tableRows": [{"tableCells": [
            {"content": [{"paragraph": {"elements": [
                {"textRun": {"content": "in cell", "suggestedInsertionIds": ["t1"]}}]}}]}]}]}}]}}
    sugg = extract_suggestions(doc)
    assert len(sugg) == 1 and sugg[0].text == "in cell" and sugg[0].kind == "insertion"

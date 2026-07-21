from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
META = {"d": {"id": "d", "name": "D", "mimeType": DOC, "webViewLink": "https://x/document/d/d/edit"}}
DOCUMENT = {"title": "D", "body": {"content": [
    {"paragraph": {"elements": [{"textRun": {"content": "Hello world\n"}}]}},
    {"paragraph": {"elements": [{"textRun": {"content": "Second para\n"}}]}},
    {"table": {"tableRows": [{"tableCells": [
        {"content": [{"paragraph": {"elements": [{"textRun": {"content": "cell1\n"}}]}}]},
        {"content": [{"paragraph": {"elements": [{"textRun": {"content": "cell2\n"}}]}}]},
    ]}]}},
]}}


def doc():
    return Workspace(FakeBackend(META, documents={"d": DOCUMENT})).open("d")


def test_as_text_joins_paragraphs_and_table_cells():
    t = doc().as_text()
    assert "Hello world" in t and "Second para" in t
    assert "cell1" in t and "cell2" in t


def test_paragraphs_are_split():
    ps = doc().paragraphs
    assert ps[0] == "Hello world" and ps[1] == "Second para"

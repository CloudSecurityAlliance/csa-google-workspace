"""Test that all public data types are importable from package root."""
import csa_google_workspace as cw


def test_comment_importable():
    assert hasattr(cw, "Comment") and isinstance(cw.Comment, type)


def test_author_importable():
    assert hasattr(cw, "Author") and isinstance(cw.Author, type)


def test_reply_importable():
    assert hasattr(cw, "Reply") and isinstance(cw.Reply, type)


def test_location_importable():
    assert hasattr(cw, "Location") and isinstance(cw.Location, type)


def test_suggestion_importable():
    assert hasattr(cw, "Suggestion") and isinstance(cw.Suggestion, type)


def test_slide_importable():
    assert hasattr(cw, "Slide") and isinstance(cw.Slide, type)


def test_all_includes_exported_types():
    expected = {"Comment", "Author", "Reply", "Location", "Suggestion", "Slide",
                "Workspace", "Doc", "Sheet", "Slides", "exceptions"}
    assert expected.issubset(set(cw.__all__))

"""Wire shapes assembled by hand, and the three that nothing was calling.

These are the functions that turn a library object into the dict a client receives. Each is
small, and each is a place where a field can go missing without anything failing - a caller
gets a dict, it has the keys it has, and the one that is absent is simply never read.

The restriction case is the sharp one. `restrictions_out` has to distinguish *"Drive says this
file is unrestricted"* from *"Drive told us nothing"*, and the second must never render as the
first: reporting an unknown restriction as absent is the dangerous direction, because the
caller's next move is to try the thing.
"""
from __future__ import annotations

from csa_google_workspace.mcp import _schemas


class Doc:
    id, name, type, url = "d1", "A Draft", "document", "https://docs.google.com/d/d1"


class Actor:
    def __init__(self, display_name=None, email=None, me=False):
        self.display_name, self.email, self.me = display_name, email, me


def Restrictions(**kw):
    """The real `FileRestrictions`, not a stand-in.

    A hand-written double here would be exactly the mistake these tests are about: it would
    have whatever attributes the test happened to give it, and a field added to the real
    dataclass and never rendered would go unnoticed - which is the defect shape, not a
    convenience.
    """
    from csa_google_workspace.restrictions import FileRestrictions

    defaults = dict(can_copy=True, can_share=True, can_edit=True, can_comment=True,
                    writers_can_share=True)
    return FileRestrictions(**{**defaults, **kw})


def test_document_out_carries_the_four_fields_a_client_needs():
    """`url` above all: a client with an id and no link cannot hand the document to a person,
    and constructing one from the id requires knowing Drive's URL shape per file type."""
    assert _schemas.document_out(Doc()) == {
        "id": "d1", "name": "A Draft", "type": "document",
        "url": "https://docs.google.com/d/d1"}


class TestAnActorOnAFile:
    def test_a_named_person_carries_both_identifiers(self):
        out = _schemas._actor_out(Actor("Kurt Seifried", "kurt@example.org", me=True))
        assert out == {"display_name": "Kurt Seifried", "email": "kurt@example.org",
                       "me": True}

    def test_an_actor_drive_would_not_name_is_none_rather_than_empty(self):
        """Drive omits the address on a file shared outside the domain, and on a deleted
        account. `None` says "Drive did not tell us"; `""` would render as a blank address
        beside a confident-looking display name."""
        out = _schemas._actor_out(Actor(None, None))
        assert out == {"display_name": None, "email": None, "me": False}

    def test_me_is_the_field_that_answers_is_this_mine(self):
        """A display name is neither unique nor stable, and matching on it is how a sweep
        attributes somebody else's file to the person running it."""
        assert _schemas._actor_out(Actor("A", "a@b.c", me=False))["me"] is False


class TestReportingRestrictions:
    def test_unknown_is_never_rendered_as_unrestricted(self):
        """The dangerous direction. "Drive returned no restriction information" and "Drive
        permits everything" lead to opposite next moves, and only one of them is a claim this
        server can make.

        `unknown` is DERIVED - every field None - rather than a flag, so the fixture is an
        empty `FileRestrictions`, which is exactly what `from_api` builds from a Drive
        response that carried no `capabilities`. Setting a stub flag would have tested a
        state the real type cannot reach."""
        from csa_google_workspace.restrictions import FileRestrictions

        nothing_known = FileRestrictions()
        assert nothing_known.unknown is True, "the fixture does not model the state"

        out = _schemas.restrictions_out("f", nothing_known, None)
        assert "NO restriction information" in out["detail"]
        assert "not the same as unrestricted" in out["detail"]

    def test_an_unrestricted_file_says_what_is_permitted(self):
        out = _schemas.restrictions_out("f", Restrictions(), None)
        assert "permits editing, commenting, sharing and copying" in out["detail"]

    def test_each_refusal_is_named(self):
        out = _schemas.restrictions_out(
            "f", Restrictions(can_copy=False, can_share=False), None)
        assert "Drive will refuse: copying, sharing." in out["detail"]

    def test_writers_cannot_reshare_is_called_out_as_stronger_than_our_own_gate(self):
        """`writersCanShare=false` is enforced by Drive against EVERY client. This server's
        own `file.share` capability binds only its own calls, so the two are different
        guarantees and conflating them would overstate what the capability buys."""
        out = _schemas.restrictions_out("f", Restrictions(writers_can_share=False), None)

        assert "writersCanShare=false" in out["detail"]
        assert "enforced by Drive against every client" in out["detail"]
        assert "file.share" in out["detail"]

    def test_the_drive_id_travels_with_the_answer(self):
        """A file in a shared drive is restricted by that drive's settings as well as its own,
        so which drive it is in is part of the answer rather than context."""
        out = _schemas.restrictions_out("f", Restrictions(), "drive9")
        assert out["file_id"] == "f" and out["drive_id"] == "drive9"


class TestContextThatIsAbsent:
    def test_no_context_is_none_rather_than_an_empty_shape(self):
        """A caller branches on the whole object. An empty context with blank fields would
        pass a `if ctx:` check and then render as a quote of nothing."""
        assert _schemas.context_out(None) is None

    def test_a_context_comes_back_whole(self):
        class Ctx:
            text = "the shared responsibility model"
            kind = "paragraph"
            note = ""
            paragraph_index, paragraph_total = 6, 9
            heading_path = ("Chapter 2", "Controls")
            truncated = False
            candidates = ()

        out = _schemas.context_out(Ctx())
        assert out is not None and out["text"] == "the shared responsibility model"

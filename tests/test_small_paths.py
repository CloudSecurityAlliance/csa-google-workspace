"""The last handful of paths, gathered rather than scattered.

None of these is a feature. Each is a branch that exists because something can arrive in a
shape the happy path does not describe - an element with no text, a quote that is not in the
passage, a token file somebody moved, a scope with nothing in it. They were the residue of the
climb to 100%, and collecting them in one file is how they stay findable.

Two of them are about NOT PRINTING things, which is the reason this file is not merely
tidying: `_Block.__repr__` holds document text, and the feedback scope describes itself by
size rather than by content.
"""
from __future__ import annotations

import pytest

from csa_google_workspace import _context, suggestions


class TestBlocksDoNotPrintDocumentText:
    def test_a_block_repr_says_how_much_text_not_what_it_says(self):
        """`_Block` is internal and the generated repr would print the passage. An embedder
        logging an object it did not write is the ordinary way document content reaches a log
        file, and "internal" is not a property a logger checks."""
        block = _context._Block("paragraph", "The 2026 layoff plan, in full", "NORMAL_TEXT", {})
        printed = repr(block)

        assert "layoff" not in printed
        assert "chars=29" in printed and "paragraph" in printed

    def test_it_still_says_enough_to_debug_with(self):
        block = _context._Block("table", "x" * 400, None, {})
        assert "kind='table'" in repr(block) and "chars=400" in repr(block)


class TestStructuralElementsWithNothingInThem:
    def test_an_element_that_is_neither_paragraph_nor_table_becomes_an_empty_block(self):
        """A section break, a table of contents, an embedded object. It has to occupy a
        POSITION in the block list - dropping it would shift every index after it, and the
        indices are what "the nearest element with text" is measured against."""
        document = {"body": {"content": [
            {"paragraph": {"elements": [{"textRun": {"content": "First.\\n"}}]}},
            {"sectionBreak": {"sectionStyle": {}}},
            {"paragraph": {"elements": [{"textRun": {"content": "Second.\\n"}}]}},
        ]}}
        blocks = _context._blocks(document)

        assert [b.kind for b in blocks] == ["paragraph", "other", "paragraph"]
        assert blocks[1].text == ""

    def test_a_table_is_a_block_of_its_own_kind(self):
        document = {"body": {"content": [{"table": {"tableRows": []}}]}}
        assert [b.kind for b in _context._blocks(document)] == ["table"]


class TestMarkingTheSelection:
    def test_a_quote_that_is_present_is_delimited_once(self):
        """First occurrence only: within one block the selection is unique, and marking every
        occurrence would claim the comment is attached to all of them."""
        marked = _context._delimit("alpha beta alpha", "alpha")
        assert marked.count(_context.OPEN) == 1
        assert marked.startswith(f"{_context.OPEN}alpha{_context.CLOSE}")

    @pytest.mark.parametrize("text, quote", [
        pytest.param("the passage", "not in here", id="quote-absent"),
        pytest.param("the passage", "", id="no-quote"),
    ])
    def test_a_quote_that_is_not_there_leaves_the_text_alone(self, text, quote):
        """Drive's `quotedFileContent` can disagree with the current document - somebody
        edited the passage after commenting. Returning the text unmarked is right; raising
        would lose the context entirely over a stale quote."""
        assert _context._delimit(text, quote) == text


class TestACommentOnSomethingWithNoText:
    """`nearest_text` is in the `context_kind` enum a consumer reads, and `build` cannot
    produce it (#492).

    The guard that would is `elif not block.has_text`, and by the time it runs `quote` is
    non-blank - the first guard returns `no_quote` otherwise - and `block` is the first one
    CONTAINING that quote, so `block.text.strip()` cannot be empty.

    The case it was written for is real; it just arrives somewhere else. A comment anchored to
    an image or a section break reaches `build` with NO quote, because Drive has nothing to
    put in `quotedFileContent`, and lands in `no_quote` - whose note already names images,
    drawings and cells.
    """

    def test_a_text_free_anchor_arrives_as_no_quote_and_says_why(self):
        document = {"body": {"content": [
            {"paragraph": {"elements": [{"textRun": {"content": "Before.\n"}}]}},
            {"sectionBreak": {"sectionStyle": {}}},
        ]}}
        context = _context.build(document, None)

        assert context is not None and context.kind == _context.KIND_NO_QUOTE
        assert "not text" in context.note and "anchor_state" in context.note

    def test_no_input_produces_nearest_text(self):
        """The claim behind the pragma, asserted rather than asserted-in-a-comment. An
        exhaustive sweep over the shapes that could plausibly reach that branch - an empty
        paragraph, a whitespace paragraph, a section break, an empty table, a heading - with
        every quote drawn from the document's own text.

        If somebody reorders the guards in `build` to make it reachable, this fails and points
        at #492 rather than leaving a stale pragma behind."""
        import itertools

        def para(text, style=None):
            element = {"paragraph": {"elements": [{"textRun": {"content": text}}]}}
            if style:
                element["paragraph"]["paragraphStyle"] = {"namedStyleType": style}
            return element

        pieces = [para("Alpha.\n"), para("\n"), para("   \n"), {"sectionBreak": {}},
                  {"table": {"tableRows": []}}, para("Heading", "HEADING_1"), para("Beta.\n")]
        quotes = ["Alpha.", "Beta.", "Heading", " ", "\n", "A", "."]

        for size in (1, 2, 3):
            for combo in itertools.permutations(pieces, size):
                document = {"body": {"content": list(combo)}}
                for quote in quotes:
                    context = _context.build(document, quote)
                    assert context is None or context.kind != _context.KIND_NEAREST, (
                        f"#492 says this is unreachable, and {quote!r} reached it - the "
                        f"pragma on that branch is now stale")


class TestSuggestionRunsWithNoText:
    def test_an_element_that_is_not_a_text_run_is_skipped(self):
        """A paragraph's elements can be inline images, footnote references, page breaks.
        None carries suggestion state, and reaching for `content` on one raises."""
        groups: dict = {}
        suggestions._collect({"paragraph": {"elements": [
            {"inlineObjectElement": {"inlineObjectId": "img1"}},
            {"pageBreak": {}},
        ]}}, groups)

        assert groups == {}, "a non-text element produced a suggestion out of nothing"

    def test_an_element_with_no_paragraph_at_all_is_skipped(self):
        groups: dict = {}
        suggestions._collect({"table": {"tableRows": []}}, groups)
        assert groups == {}


class TestDescribingAScopeBySize:
    """`report_a_problem` assembles a report containing no ids and no document content. The
    scope is part of it, so it is described by SIZE - a list of file ids in a public issue is
    the thing the whole tool exists to avoid."""

    @staticmethod
    def described(**kw):
        from csa_google_workspace.mcp._tools.feedback import _scope_shape

        return _scope_shape(type("Scope", (), kw)())

    def test_an_empty_scope_says_it_fails_closed(self):
        """Not "0 files", which reads as a count somebody might try to raise. An allowlist
        with no usable entries REFUSES everything, and saying so is the difference between a
        bug report and a configuration question."""
        assert self.described(all_files=False, ids=()) == "nothing (fails closed)"

    def test_an_unrestricted_scope_says_so_in_words(self):
        assert self.described(all_files=True, ids=()) == \
            "every file the credentials can reach"

    @pytest.mark.parametrize("count, expected", [(1, "1 file"), (3, "3 files")])
    def test_a_narrowed_scope_is_a_count_and_never_the_ids(self, count, expected):
        ids = tuple(f"file-id-{i}" for i in range(count))
        described = self.described(all_files=False, ids=ids)

        assert described == expected
        for one in ids:
            assert one not in described, "a file id reached a public bug report"

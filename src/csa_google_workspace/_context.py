"""The passage around a comment's anchor — because the anchor records where a comment was
ATTACHED, not what it is ABOUT.

Usually those coincide. Often enough they do not, and no exotic cause is needed: a reviewer
selects three words of a paragraph-length point, clicks the line above the one they meant, or
writes *"at the end of this paper the conclusion is weak"* while the comment sits on page 1.
A human reading the comment beside its passage notices instantly and compensates without
registering it as an event; a consumer treating `quoted_text` as the subject cannot.

So this treats the anchor as a **localization hint that gets tested**, which degrades
gracefully: a sloppy selection plus its surrounding paragraph still finds the right text,
whereas a sloppy selection believed absolutely produces a confident wrong answer (#358).

## Why it locates by QUOTED TEXT and not by the anchor

Because the anchor cannot be used. MEASURED 2026-09-02
(`experiments/docs-anchor-states/RESULTS.md`): a real Docs anchor is an opaque `kix.…` id and a
Sheets anchor an opaque `workbook-range` — a **key, not a coordinate**. Google's one published
example carries a `line` number and is not what the editors produce.

That looked fatal and is not, because of two other measurements: the editor **expands a bare
caret to its enclosing word**, and **refuses to comment on empty space at all**. So quoted text
is present wherever text is, and the only anchored comments without it are on non-text objects,
where there is no textual context to give anyway.

## What it is strict about, and why that is the right call FOR NOW

Everything here is deterministic: the chunk is chosen by structure, and `context_kind` says
which rule fired. **The strictness is a property of the producer, not the consumer** — an AI
reading this could cope with fuzziness, but software choosing the passage must be explainable or
nobody can say why a given chunk came back.

A future AI-chosen variant is additive rather than a redesign: it adds a member to `KINDS` and
puts its reasoning in `note`. Two things are left in place for it — the vocabulary is closed so
a new member is a deliberate act, and **the context is not promised to be contiguous**: disjoint
spans are joined by `GAP`, unused today.

## The one honest failure

A quote occurring **more than once** cannot be placed, and there is no tiebreaker because the
anchor is opaque. Short selections make this *more* likely, so the comments that most need
context are the ones most at risk of not getting it. Reported as `KIND_AMBIGUOUS` with a count,
never guessed — a marker in the wrong place is worse than no marker, because it is not visibly
wrong.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._content import _element_text, _para_text, doc_tab_bodies

# The selection, marked IN PLACE inside the passage. Seeing where it sits is the whole
# under-selection signal: three words at the head of a 400-character paragraph is visible at a
# glance and needs no computation.
OPEN, CLOSE = "⟦", "⟧"          # ⟦ ⟧ — not brackets that occur in prose
GAP = " … "                               # between disjoint spans. Reserved; see the docstring.

# CLOSED vocabulary, for the reason the threat-model statuses are closed: a near-miss like
# "expanded" reads as meaningful while saying less than any real member.
KIND_PARAGRAPH = "paragraph"              # the enclosing paragraph
KIND_PARAGRAPHS = "paragraphs"            # the selection spans several
KIND_HEADING = "heading_and_following"    # the selection is a heading; its content follows it
KIND_TABLE = "table"                      # the whole enclosing table
KIND_TABLE_ROW = "table_row"              # too big for the cap: the row plus the header row
KIND_NEAREST = "nearest_text"             # the element has no text; nearest that does
KIND_NOT_FOUND = "not_found"              # we searched the document and it is not there
KIND_SPANNING = "spanning"                # the selection itself crosses structural boundaries
KIND_NO_QUOTE = "no_quote"                # the comment quotes nothing, so there is no passage
KIND_UNSUPPORTED = "unsupported"          # this document type has no passage lookup here
KIND_AMBIGUOUS = "ambiguous"              # the quote occurs more than once
KINDS = frozenset({KIND_PARAGRAPH, KIND_PARAGRAPHS, KIND_HEADING, KIND_TABLE, KIND_TABLE_ROW,
                   KIND_NEAREST, KIND_NOT_FOUND, KIND_AMBIGUOUS,
                   KIND_NO_QUOTE, KIND_UNSUPPORTED, KIND_SPANNING})

# The last two exist so that a `context` a caller ASKED FOR always explains itself, which
# makes `null` mean exactly one thing: nobody asked. Before, `null` meant three - "there is no
# passage to find", "this file type is not supported here", and "you did not request it" - and
# a consumer could not tell "we looked and found nothing" from "we never looked". That is the
# same asymmetry `labels.py` and `_inventory.py` are built around, and the dangerous direction
# is identical: silence reading as absence.

# A guard, never the unit of measurement. Structural expansion is the point (#358 prefers it
# over character counts because it respects boundaries) - but a single legal-document paragraph
# can run to thousands of words, so expansion stops here and SAYS it stopped. Truncation the
# reader cannot see is a claim that this was the whole passage.
MAX_CHARS = 4000

_HEADINGS = ("HEADING_", "TITLE", "SUBTITLE")


@dataclass
class Context:
    """The passage, plus why it is this passage.

    `kind` is for branching, `note` is for a person. Both, because a consumer wants to switch on
    the rule that fired and a human reading a register wants the sentence — and without either
    they receive a paragraph they did not select and cannot tell the feature from a bug.
    """
    text: str
    kind: str
    note: str
    paragraph_index: int | None = None      # 1-based, among paragraphs
    paragraph_total: int | None = None      # so "at the end of this paper" is checkable
    heading_path: tuple[str, ...] = ()      # outermost first
    truncated: bool = False
    # WHERE the candidates are, when the quote is ambiguous. Facts, so the caller can decide:
    # a consumer holding the comment text can often tell which of four occurrences was meant,
    # and we cannot. Empty unless `kind == KIND_AMBIGUOUS`.
    candidates: tuple[tuple[int | None, tuple[str, ...]], ...] = ()

    def __repr__(self) -> str:
        # Redacted like every model here: this is document text and embedders log these.
        return (f"Context(kind={self.kind!r}, chars={len(self.text)}, "
                f"truncated={self.truncated})")


@dataclass(repr=False)
class _Block:
    """One structural element, flattened to what the rules need."""
    kind: str                  # "paragraph" | "table" | "other"
    text: str
    style: str | None          # namedStyleType, paragraphs only
    element: dict[str, Any]

    @property
    def is_heading(self) -> bool:
        return self.style is not None and self.style.startswith(_HEADINGS)

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())

    def __repr__(self) -> str:
        # Internal, but it holds DOCUMENT TEXT and the generated repr would print it. The
        # redaction rule here is about where text can leak, not about which classes are public.
        return f"_Block(kind={self.kind!r}, style={self.style!r}, chars={len(self.text)})"


def _blocks(document: dict) -> list[_Block]:
    """Every structural element with text, in document order, across every tab.

    Deliberately built on `doc_tab_bodies`, which already handles the trap that
    `documents.get` without `includeTabsContent` returns the FIRST TAB ONLY while looking
    complete (measured, `experiments/docs-tabs/`).
    """
    out: list[_Block] = []
    for _title, content in doc_tab_bodies(document):
        for el in content:
            if "paragraph" in el:
                style = el["paragraph"].get("paragraphStyle", {}).get("namedStyleType")
                out.append(_Block("paragraph", _para_text(el["paragraph"]), style, el))
            elif "table" in el:
                out.append(_Block("table", _element_text(el), None, el))
            else:
                out.append(_Block("other", "", None, el))
    return out


def _occurrences(blocks: list[_Block], quote: str) -> int:
    return sum(b.text.count(quote) for b in blocks)


def _rows_text(element: dict[str, Any]) -> list[str]:
    return ["".join(_element_text(c) for cell in row.get("tableCells", [])
                    for c in cell.get("content", []))
            for row in element.get("table", {}).get("tableRows", [])]


def _cap(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_CHARS:
        return text, False
    return text[:MAX_CHARS] + f"… [truncated at {MAX_CHARS} characters]", True


def _heading_path(blocks: list[_Block], at: int) -> tuple[str, ...]:
    """The heading chain above `at`, outermost first.

    Walks BACKWARDS taking each heading that is more senior than the last one taken, so
    `H1 › H2 › H3` comes back whole and a later sibling `H2` does not displace its parent `H1`.
    """
    path: list[str] = []
    seen = 99
    for b in reversed(blocks[:at + 1]):
        if not b.is_heading or not b.style:
            continue
        style = b.style
        level = int(style[len("HEADING_"):]) if style.startswith("HEADING_") else 0
        if level < seen:
            path.append(b.text.strip())
            seen = level
        if level == 0:                     # TITLE/SUBTITLE: nothing outranks it
            break
    return tuple(reversed(path))


def _spanning(blocks: list[_Block], quote: str) -> tuple[int, int, int] | None:
    """`(count, first_block, last_block)` for a quote that crosses structural elements.

    **#405: a real 830-character editor selection crossed a paragraph boundary and was reported
    as NOT IN THE DOCUMENT** — while this package's own `as_text()` found it exactly once. The
    per-element search could not match it by construction: a quote containing the newline
    between two paragraphs is inside neither of them.

    That made it the most confident possible wrong answer. `not_found` says *"WE SEARCHED THE
    DOCUMENT AND THIS QUOTED TEXT IS NOT IN IT"* in capitals, and listed three causes it said
    could not be told apart. There was a fourth it did not contemplate: **present, and
    unfindable by an element-scoped search.**

    Searches the concatenation of the block texts, which is the same string `_content.doc_text`
    builds for a single-tab document — so this function and `as_text()` cannot disagree about
    whether a quote is present, which is the property the bug report actually asked for.

    Returns `None` when the quote is not in the concatenation either, so a genuine absence is
    still a genuine absence. Reports the **count** as well, because a spanning quote can occur
    twice as easily as a contained one and guessing which is the same error either way.
    """
    joined = "".join(b.text for b in blocks)
    count = joined.count(quote)
    if count == 0:
        return None
    start = joined.index(quote)
    end = start + len(quote)
    # Walk the blocks accumulating offsets, and record which ones the match touches. A block
    # is touched when it overlaps [start, end) - not merely when it contains the start, which
    # would report only the first of three spanned paragraphs.
    first = last = None
    at = 0
    for i, b in enumerate(blocks):
        block_end = at + len(b.text)
        if at < end and block_end > start:
            first = i if first is None else first
            last = i
        at = block_end
    if first is None or last is None:      # pragma: no cover - implied by count > 0
        return None
    return count, first, last


def _paragraph_position(blocks: list[_Block], at: int) -> tuple[int | None, int]:
    """(1-based index among paragraphs, total paragraphs).

    Reported so a prose claim like *"at the end of this paper"* is CHECKABLE by the caller.
    Deliberately not compared here - deciding whether the comment is about where it sits is
    judgement, and #358 asks for facts (`would two consumers with different purposes want the
    identical value?` - an index, yes; a verdict, no).
    """
    paragraphs = [i for i, b in enumerate(blocks) if b.kind == "paragraph" and b.has_text]
    total = len(paragraphs)
    return (paragraphs.index(at) + 1 if at in paragraphs else None), total


def _delimit(text: str, quote: str) -> str:
    """Mark the selection in place. First occurrence only — within one block it is unique."""
    if not quote or quote not in text:
        return text
    return text.replace(quote, f"{OPEN}{quote}{CLOSE}", 1)


def build(document: dict, quote: str | None, *, paragraphs: int = 0) -> Context | None:
    """The passage around `quote`, or `None` when there is nothing to place.

    `None` rather than a `Context` for a comment with no quoted text: that is a file-level
    comment or one on a non-text object, and neither has a passage. Saying so with a `kind`
    would imply a failure where there is simply no question.
    """
    if not quote or not quote.strip():
        return Context("", KIND_NO_QUOTE,
                       "This comment quotes nothing, so there is no passage to find. It is "
                       "either about the whole file or attached to something that is not text "
                       "- an image, a drawing, a cell. `anchor_state` says which. This is not "
                       "a failure and not a missing value: there was no question to answer.")

    blocks = _blocks(document)
    found = _occurrences(blocks, quote)
    if found == 0:
        # Before declaring absence, ask whether the quote spans elements (#405). The
        # element-scoped search above cannot see such a quote at all, and answering
        # "not in the document" for a passage `as_text()` can find is worse than any
        # miss - it is a confident wrong answer about the caller's own document.
        span = _spanning(blocks, quote)
        if span is not None:
            count, first, last = span
            if count > 1:
                return Context("", KIND_AMBIGUOUS,
                               f"The quoted text spans a structural boundary and occurs "
                               f"{count} times in this document, so which one the comment "
                               f"points at cannot be determined here. This is EXPECTED for a "
                               f"repeated passage and does not mean the document is damaged; "
                               f"the candidates are not reported for a spanning quote because "
                               f"it has no single enclosing element to name.")
            text = "".join(b.text for b in blocks[first:last + 1])
            marked, truncated = _cap(_delimit(text, quote))
            index, total = _paragraph_position(blocks, first)
            n = last - first + 1
            return Context(marked, KIND_SPANNING,
                           f"The selection itself crosses {n} structural elements, so the "
                           f"passage is exactly the {n} it touches - no expansion was inferred, "
                           f"and for this one case the quote IS the passage. A selection like "
                           f"this is deliberate rather than sloppy: somebody dragged across a "
                           f"boundary on purpose."
                           + (" Truncated at the character limit." if truncated else ""),
                           paragraph_index=index, paragraph_total=total,
                           heading_path=_heading_path(blocks, first), truncated=truncated)
        return Context("", KIND_NOT_FOUND,
                       "WE SEARCHED THE DOCUMENT AND THIS QUOTED TEXT IS NOT IN IT. The search "
                       "ran and completed - this is a finding, not an error and not a missing "
                       "value. Three things cause it and they cannot be told apart from here: "
                       "the passage was edited or deleted after the comment was written; the "
                       "comment belongs to a different revision; or the quoted text was NEVER "
                       "in this document, which is possible because whoever created the "
                       "comment supplies that field and Google validates it against nothing. "
                       "A fourth cause - the quote spanning a paragraph boundary - USED to "
                       "land here wrongly and no longer does (#405): a spanning quote is now "
                       "found and reported as `spanning`. "
                       "Do not repeat the quoted text as something the document says.")
    if found > 1:
        # MEASURED while building this, on a nine-paragraph document: a comment placed with a
        # bare caret quotes the single word the editor snapped to, and a single word is
        # ambiguous almost immediately. So this is not a rare edge - it is the DOMINANT
        # outcome for the commonest form of under-selection, which is why it reports the
        # candidate locations rather than just refusing.
        where = tuple((_paragraph_position(blocks, i)[0], _heading_path(blocks, i))
                      for i, b in enumerate(blocks) if quote in b.text)
        return Context("", KIND_AMBIGUOUS,
                       f"The quoted text occurs {found} times in this document, so which one "
                       f"the comment points at cannot be determined here - the Drive anchor is "
                       f"an opaque id and carries no position. This is EXPECTED for a very "
                       f"short selection (a comment placed without selecting anything quotes "
                       f"one word) and is not a sign of a damaged document. `candidates` gives "
                       f"each location; the comment's own text is usually enough to tell which "
                       f"was meant, and that judgement is the caller's.",
                       paragraph_total=_paragraph_position(blocks, -1)[1], candidates=where)

    at = next(i for i, b in enumerate(blocks) if quote in b.text)
    block = blocks[at]
    index, total = _paragraph_position(blocks, at)
    path = _heading_path(blocks, at)

    if block.kind == "table":
        whole = block.text
        if len(whole) <= MAX_CHARS:
            text, kind = whole, KIND_TABLE
            note = "The selection is inside a table; the context is the whole table."
        else:
            # Degrade to the row plus the header row rather than truncating mid-table: the same
            # instinct as the row/column headers on a Sheets cell comment, and a 200-row table
            # would otherwise blow any cap and tell the reader nothing.
            rows = _rows_text(block.element)
            here = next((r for r in rows if quote in r), "")
            header = rows[0] if rows and rows[0] is not here else ""
            text = "\n".join(p for p in (header, here) if p)
            kind = KIND_TABLE_ROW
            note = (f"The selection is inside a {len(rows)}-row table, which is too large to "
                    f"return whole; the context is its row plus the header row.")
    elif block.is_heading:
        # Forward only, and it is a STRUCTURAL fact rather than an inference: namedStyleType
        # says this element heads what follows. Consecutive headings are skipped, because two
        # labels and no prose is the thing being fixed.
        parts = [block.text]
        for nxt in blocks[at + 1:]:
            if nxt.is_heading or not nxt.has_text:
                continue
            parts.append(nxt.text)
            break
        text, kind = "".join(parts), KIND_HEADING
        note = ("The selection is a heading, so the context is the heading plus the first "
                "following body paragraph - a heading's subject is what it heads.")
    elif not block.has_text:                        # pragma: no cover - UNREACHABLE, see #492
        # `quote` is non-blank (the first guard returns KIND_NO_QUOTE otherwise) and `at` is
        # the first block CONTAINING it, so `block.text.strip()` cannot be empty and this is
        # never true. Confirmed by exhaustive sweep, not only by reading.
        #
        # Kept rather than deleted because `nearest_text` is in the `context_kind` enum a
        # consumer reads, and removing a documented value is a contract change with a
        # CHANGELOG line, not a tidy-up. #492 carries the decision: delete it, or reorder the
        # guards so a text-free anchor lands here instead of in `no_quote`.
        nearest = next((b.text for b in blocks[at + 1:] if b.has_text), "") or \
                  next((b.text for b in reversed(blocks[:at]) if b.has_text), "")
        text, kind = nearest, KIND_NEAREST
        note = ("The element the comment is attached to has no text of its own, so the context "
                "is the nearest element that does.")
    else:
        text, kind = block.text, KIND_PARAGRAPH
        note = "The context is the paragraph the selection sits in."

    if paragraphs > 0:
        before = [b.text for b in blocks[max(0, at - paragraphs):at] if b.has_text]
        after = [b.text for b in blocks[at + 1:at + 1 + paragraphs] if b.has_text]
        text = "".join([*before, text, *after])
        kind = KIND_PARAGRAPHS if kind == KIND_PARAGRAPH else kind
        note += f" Extended by up to {paragraphs} element(s) either side, as requested."

    text, truncated = _cap(_delimit(text, quote))
    if truncated:
        note += " It was truncated at the character limit."
    return Context(text=text, kind=kind, note=note, paragraph_index=index,
                   paragraph_total=total, heading_path=path, truncated=truncated)

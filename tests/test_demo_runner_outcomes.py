"""What the runner does when a step does NOT simply work, and what the narration says.

`test_demo.py` exercises the happy path against a fake Drive. The branches left over are the
ones that decide whether a run is a red build or a green one, and they are not
interchangeable - the runner has three statuses, and which one a situation gets is a claim
about whose fault it was:

    skipped   the demonstration could not stage this here (capability off, nothing to tidy,
              an upstream step produced nothing, the person said no)
    failed    the server did the wrong thing
    ok        it worked

The demo IS this project's end-to-end test, so `failed` is what a CI job reads. Calling a
staging problem a failure makes an ordinary run red forever; calling a server fault a skip
makes a broken server green.
"""
from __future__ import annotations

import pytest

from csa_google_workspace.demo._plan import Outcome, Report, State, Step
from csa_google_workspace.demo._runner import NOT_EXERCISED, Runner, coverage, narrator, render


class FakeResult:
    def __init__(self, structured_content):
        self.structured_content = structured_content


#: `answer=None` has to mean "the tool has no output schema", which is a state the runner
#: branches on - so the default cannot be None as well.
UNSET = object()


class FakeServer:
    """Answers `call_tool` from a script and `list_tools` from a fixed roster."""

    def __init__(self, *, answer=UNSET, raises=None, tools=()):
        self.answer, self.raises, self._tools = answer, raises, tools
        self.called = []

    async def call_tool(self, name, args):
        self.called.append((name, args))
        if self.raises is not None:
            raise self.raises
        return FakeResult({} if self.answer is UNSET else self.answer)

    async def list_tools(self):
        return [type("T", (), {"name": name})() for name in self._tools]


def step(**kw):
    base = {"tool": "list_recent_files", "narrate": "list the recent files",
            "args": lambda state: {}}
    return Step(**{**base, **kw})


def run_one(server, the_step, state=None, enabled=("file.create",), confirm=None):
    runner = Runner(server, confirm=confirm)
    return runner._one(the_step, state if state is not None else State(), set(enabled))


class TestWhoseFaultItWas:
    def test_a_capability_that_is_off_is_a_skip_naming_the_capability(self):
        """A disabled capability is a DEPLOYMENT choice, not a defect. The message names it so
        the reader can tell "this install is narrow" from "this tool is broken"."""
        outcome = run_one(FakeServer(), step(requires="file.share"), enabled=("file.create",))
        assert outcome.status == "skipped"
        assert "file.share" in outcome.detail

    def test_the_person_saying_no_is_a_skip(self):
        """The attended mode's whole point. It must not count against the run."""
        outcome = run_one(FakeServer(), step(), confirm=lambda s: False)
        assert outcome.status == "skipped"
        assert outcome.detail == "you chose to skip this one"

    def test_saying_yes_runs_it(self):
        server = FakeServer()
        assert run_one(server, step(), confirm=lambda s: True).status == "ok"
        assert server.called, "confirm returning True must actually call the tool"

    def test_a_cleanup_slot_with_nothing_left_is_a_skip(self):
        """There are deliberately more cleanup slots than files, so `IndexError` out of
        `args` is the NORMAL way the tail of the cleanup ends - not an error."""
        def nothing_left(state):
            raise IndexError("pop from empty list")

        outcome = run_one(FakeServer(), step(args=nothing_left))
        assert outcome.status == "skipped"
        assert outcome.detail == "nothing left to tidy"

    def test_a_missing_upstream_value_is_a_skip_not_a_second_failure(self):
        """An earlier step did not produce what this one needs. The fault is upstream and is
        already recorded there; reporting it again would multiply one defect into a column of
        red that all has the same cause."""
        def needs_a_document(state):
            return {"fileId": state["document_id"]}

        outcome = run_one(FakeServer(), step(args=needs_a_document))
        assert outcome.status == "skipped"
        assert "document_id" in outcome.detail

    def test_a_tool_that_raises_is_a_failure(self):
        """The server did the wrong thing. Type AND message, because "PolicyError" and
        "HttpError 403" are different problems with the same shape."""
        outcome = run_one(FakeServer(raises=RuntimeError("Drive said no")), step())
        assert outcome.status == "failed"
        assert outcome.detail == "RuntimeError: Drive said no"

    def test_an_optional_step_that_raises_is_only_a_skip(self):
        """`optional` marks the steps that need something the environment may not have. They
        are reported, and they do not make the run red."""
        outcome = run_one(FakeServer(raises=RuntimeError("no recipient")),
                          step(optional=True))
        assert outcome.status == "skipped"
        assert "RuntimeError" in outcome.detail

    def test_a_failure_is_still_timed(self):
        """The elapsed time is recorded before the status is decided, so a slow failure is
        distinguishable from an instant one - which is most of what tells a timeout apart
        from a rejection."""
        outcome = run_one(FakeServer(raises=RuntimeError("x")), step())
        assert outcome.seconds >= 0.0

    def test_a_result_the_step_cannot_read_is_a_failure_that_keeps_the_result(self):
        """`captures` raising means the tool answered in a shape the plan did not expect -
        a real server fault. The raw content is kept ON the outcome, because the next
        question is always "what did it actually return?"."""
        def cannot_read(state, content):
            raise KeyError("id")

        server = FakeServer(answer={"unexpected": "shape"})
        outcome = run_one(server, step(captures=cannot_read))
        assert outcome.status == "failed"
        assert "could not read the result" in outcome.detail
        assert outcome.result == {"unexpected": "shape"}

    def test_a_step_that_captures_threads_state_to_the_next_one(self):
        state = State()
        server = FakeServer(answer={"fileId": "abc"})
        outcome = run_one(server, step(captures=lambda s, c: s.update(doc=c["fileId"])),
                          state=state)
        assert outcome.status == "ok"
        assert state["doc"] == "abc"

    def test_a_tool_returning_nothing_structured_is_still_ok(self):
        """`structured_content` is None for a tool with no output schema. `captures` is
        skipped rather than called with None, which would raise inside every capture."""
        server = FakeServer(answer=None)
        outcome = run_one(server, step(captures=lambda s, c: pytest.fail("called with None")))
        assert outcome.status == "ok"


class TestTheCoverageReport:
    def test_untouched_tools_are_named_as_a_gap_in_the_demonstration(self):
        """Not a gap in the server. The distinction is the difference between "go and add a
        step" and "go and fix a tool"."""
        server = FakeServer(tools=("search_files", "never_called"))
        report = Report(outcomes=[Outcome(step(tool="search_files"), "ok")])
        text = render(server, report)

        assert "### Not exercised" in text
        assert "`never_called`" in text
        assert "gap in the demonstration rather than in the server" in text

    def test_a_tool_that_cannot_be_automated_is_excused_by_name_with_its_reason(self):
        """Named rather than quietly absent: a coverage report that silently excludes things
        is a coverage report that can be gamed."""
        server = FakeServer(tools=("authenticate",))
        text = render(server, Report())

        assert "### Cannot be automated" in text
        assert "`authenticate`" in text
        assert NOT_EXERCISED["authenticate"] in text
        assert "### Not exercised" not in text, "an excused tool is not also a gap"

    def test_a_complete_run_claims_neither_section(self):
        """The branch that is false when everything registered was exercised. A report that
        printed an empty "Not exercised" heading would read as a gap with no items."""
        server = FakeServer(tools=("search_files",))
        report = Report(outcomes=[Outcome(step(tool="search_files"), "ok")])
        text = render(server, report)

        assert "### Not exercised" not in text and "### Cannot be automated" not in text

    def test_coverage_is_measured_against_the_registry_not_a_list(self):
        """A step for a tool this deployment did not register does not count as exercised -
        otherwise a flavour that drops tools would report full coverage of tools it has not
        got."""
        server = FakeServer(tools=("search_files",))
        report = Report(outcomes=[Outcome(step(tool="search_files"), "ok"),
                                  Outcome(step(tool="not_registered_here"), "ok")])
        exercised, untouched, excused = coverage(server, report)

        assert exercised == {"search_files"}
        assert untouched == set() and excused == {}

    def test_the_counts_distinguish_exercised_from_excusable(self):
        server = FakeServer(tools=("search_files", "authenticate", "never_called"))
        report = Report(outcomes=[Outcome(step(tool="search_files"), "ok")])
        assert "Tools exercised: 1 of 3 (2/3 counting the ones that cannot be automated)" \
            in render(server, report)

    def test_failed_steps_are_grouped_and_marked(self):
        report = Report(outcomes=[
            Outcome(step(tool="create_file", group="doc"), "ok"),
            Outcome(step(tool="trash_file", group="doc"), "failed", "HttpError 403"),
        ])
        text = render(FakeServer(tools=("create_file", "trash_file")), report)

        assert "### doc" in text
        assert "FAIL  trash_file" in text
        assert "- HttpError 403" in text

    def test_an_ungrouped_step_lands_under_other(self):
        text = render(FakeServer(tools=("t",)), Report(outcomes=[Outcome(step(tool="t"), "ok")]))
        assert "### other" in text


class TestNarration:
    def collect(self, *, teach):
        lines = []
        return lines, narrator(lines.append, teach=teach)

    def test_only_step_events_are_narrated(self):
        """`done` carries the whole report, and printing it here would duplicate the summary
        the CLI prints from the same object a moment later."""
        lines, on_event = self.collect(teach=False)
        on_event("done", Report())
        assert lines == []

    @pytest.mark.parametrize("status, symbol", [
        ("ok", "  ok  "), ("skipped", " skip "), ("failed", " FAIL "),
    ])
    def test_each_status_gets_its_own_marker(self, status, symbol):
        """Same width, so the narration lines up in a terminal - and FAIL is the one that has
        to be findable by eye in a run of eighty steps."""
        lines, on_event = self.collect(teach=False)
        on_event("step", Outcome(step(narrate="do the thing"), status))
        assert lines[0] == f"{symbol} do the thing"

    def test_a_detail_is_shown_under_the_step(self):
        lines, on_event = self.collect(teach=False)
        on_event("step", Outcome(step(), "skipped", "nothing left to tidy"))
        assert "        nothing left to tidy" in lines

    def test_teaching_is_wrapped_and_only_follows_a_step_that_worked(self):
        """A lesson about how Drive behaves, printed under a step that just FAILED, describes
        something the reader did not witness."""
        long = ("Drive creates the file empty and content is a separate API, which is why "
                "creating a document and writing to it are two calls rather than one.")
        lines, on_event = self.collect(teach=True)
        on_event("step", Outcome(step(teaches=long), "ok"))
        taught = [ln for ln in lines if ln.startswith("        ")]

        assert taught, "teach=True must show what the step teaches"
        assert all(len(ln) <= 8 + 76 for ln in taught), "wrapped to the narration width"
        assert " ".join(ln.strip() for ln in taught) == long

        lines, on_event = self.collect(teach=True)
        on_event("step", Outcome(step(teaches=long), "failed"))
        assert not [ln for ln in lines if ln.startswith("        ")]

    def test_teach_off_prints_the_step_and_nothing_else(self):
        lines, on_event = self.collect(teach=False)
        on_event("step", Outcome(step(teaches="something worth knowing"), "ok"))
        assert "something worth knowing" not in "".join(lines)


class TestTheShareStepWithNoRecipient:
    """`_require_share` raises `KeyError` so the runner turns it into a clean skip.

    Sharing is the one step that needs a real person's address, and `--share` is optional.
    Raising rather than returning an empty string is what keeps "no recipient given" out of
    the failure column on every ordinary run - and out of the Drive API, which would happily
    accept an empty address and produce something nobody meant.
    """

    @pytest.mark.parametrize("state", [{}, {"share_with": ""}], ids=["absent", "empty"])
    def test_no_address_raises_the_error_the_runner_reads_as_a_skip(self, state):
        from csa_google_workspace.demo._plan import _require_share

        with pytest.raises(KeyError, match="--share"):
            _require_share(state)

    def test_an_address_comes_back_as_given(self):
        from csa_google_workspace.demo._plan import _require_share

        assert _require_share({"share_with": "a@b.c"}) == "a@b.c"

    def test_the_runner_turns_that_into_a_skip_rather_than_a_failure(self):
        """The two halves joined. Asserting only that `_require_share` raises would leave the
        translation untested, and a `KeyError` reaching the failure column is precisely what
        this arrangement exists to prevent."""
        def share_args(state):
            from csa_google_workspace.demo._plan import _require_share
            return {"emailAddress": _require_share(state)}

        outcome = run_one(FakeServer(), step(tool="share_file", args=share_args))
        assert outcome.status == "skipped"
        assert "--share" in outcome.detail

"""The resources and tool that explain the server's own configuration.

These matter most when something has just been refused, which is also when the model is most
likely to guess. The point of them is that it does not have to.
"""
import asyncio

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp._config import settings_from_env
from csa_google_workspace.mcp._resources import CEILING_URI, CONFIG_URI, HELP_URI, render_config, render_help
from csa_google_workspace.mcp.server import create_server

DOC_URL = "https://docs.google.com/document/d/1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8/edit"
DOC_ID = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"
POSTURE = {
    "CSA_GW_ALLOWLIST_READ": "*",
    "CSA_GW_ALLOWLIST_MODIFY": f"{DOC_URL}  # CCM v5 mapping, per WG lead",
    "CSA_GW_CAPABILITIES": "comment.create,comment.reply",
}


def _server(env):
    return create_server(lambda: Workspace(FakeBackend({})), settings=settings_from_env(env))


def _flat(text):
    """Collapse whitespace before asserting on prose.

    These documents are hard-wrapped, so a sentence can straddle a newline — searching for
    "not a general authorization model" fails against "It is not a\ngeneral authorization
    model". Asserting on flattened text tests the wording rather than the line breaks.
    """
    return " ".join(text.split())


def _read(app, uri):
    contents = list(asyncio.run(app.read_resource(uri)))
    return contents[0].content


def _call(app, name, args=None):
    return asyncio.run(app.call_tool(name, args or {})).structured_content


# --- registration -----------------------------------------------------------

def test_all_three_resources_are_registered():
    """Three since v0.30.13: the live policy, the configuration reference, and the **ceiling** —
    what this server cannot do. The third is aimed at the model rather than the operator: an
    agent that knows there is no accept-suggestion endpoint stops inventing workarounds, and
    until it existed the only way to learn that was to fail."""
    resources = {str(r.uri): r for r in asyncio.run(_server(POSTURE).list_resources())}
    assert set(resources) == {CONFIG_URI, HELP_URI, CEILING_URI}
    for resource in resources.values():
        assert resource.name and resource.description
        assert resource.mime_type == "text/markdown"   # snake_case in mcp 2.x


def test_resources_are_absent_without_settings():
    """A library embedder wiring its own Workspace gets the document tools and none of this —
    there is no server configuration to describe."""
    app = create_server(lambda: Workspace(FakeBackend({})))
    assert asyncio.run(app.list_resources()) == []
    assert "describe_configuration" not in [t.name for t in asyncio.run(app.list_tools())]


# --- the effective-configuration resource ----------------------------------

def test_config_reports_the_actual_posture():
    text = _read(_server(POSTURE), CONFIG_URI)
    assert "Read: every file" in text
    assert "Modify: 1 document(s)" in text and DOC_ID in text
    assert "`comment.create`" in text and "`comment.reply`" in text
    assert "`file.trash`" in text                  # listed as refused


def test_config_omits_the_reasons():
    """An entry's trailing comment is written for whoever reviews the configuration and may
    name people or unannounced work — the same reasoning that keeps it out of Entry.__repr__."""
    text = _read(_server(POSTURE), CONFIG_URI)
    assert "WG lead" not in text and "CCM v5" not in text


def test_config_explains_a_closed_scope_including_why():
    """**No longer the default (v0.31.0)**, and the explanation still has to be right.

    Unset now means every file, so this is reached only when an *embedder* builds a closed scope
    through the DI seam. When they do, this text is what tells somebody why nothing works —
    deleting the test would drop the message from coverage rather than retire it."""
    from dataclasses import replace

    from csa_google_workspace.policy import Policy, Scope
    settings = replace(
        settings_from_env({}),
        policy=Policy(enabled=frozenset(),
                      read=Scope.nothing(reason="CSA_GW_ALLOWLIST_READ is not set"),
                      modify=Scope.nothing(reason="CSA_GW_ALLOWLIST_MODIFY is not set")))
    text = render_config(settings)
    assert "Read: nothing" in text and "Modify: nothing" in text
    assert "will be refused" in text
    assert "is not set" in text                    # the specific diagnosis, not just "nothing"


def test_config_reports_an_unconfigured_server_as_unrestricted():
    """The replacement for the test above, on the path an operator actually takes. The default
    being permissive is exactly the thing that must not be discoverable only by trying it."""
    text = _read(_server({}), CONFIG_URI)
    assert "every file" in text.lower()


def test_config_says_the_policy_cannot_be_changed_from_here():
    """The single most important sentence in it: without this the model tries to fix it."""
    text = _flat(_read(_server(POSTURE), CONFIG_URI))
    assert "Nothing here can be changed by a tool" in text
    assert "cannot be widened from here" in text
    assert "a retry will fail identically" in text


def test_config_reports_read_only_mode():
    assert "Read-only mode: **on**" in _read(_server({"CSA_GW_READ_ONLY": "1"}), CONFIG_URI)


def test_config_is_computed_from_settings_not_cached():
    """It must not be able to drift from what the tools enforce."""
    wide = render_config(settings_from_env({"CSA_GW_ALLOWLIST_MODIFY": "*"}))
    narrow = render_config(settings_from_env({"CSA_GW_ALLOWLIST_MODIFY": DOC_URL}))
    assert "Modify: every file" in wide
    assert "Modify: 1 document(s)" in narrow


# --- the reference resource -------------------------------------------------

def test_help_covers_every_variable():
    text = render_help()
    for variable in ("CSA_GW_ALLOWLIST_READ", "CSA_GW_ALLOWLIST_MODIFY",
                     "CSA_GW_CAPABILITIES", "CSA_GW_READ_ONLY"):
        assert variable in text


def test_help_covers_each_kind_of_mistake():
    text = _flat(render_help())
    for tell in ("no file to create", "set but empty", "stops after '/d/'", "placeholder",
                 "bare file id", "folders are not supported", "not read from a file",
                 "only the first would be allowlisted"):
        assert tell in text, tell


def test_help_states_the_limits_rather_than_leaving_them_to_be_discovered():
    text = _flat(render_help())
    assert "Folders are not supported" in text
    assert "copy" in text and "different id" in text          # copies are not included
    assert "cannot be widened from inside a session" in text


def test_help_does_not_oversell_what_this_is():
    assert "not a general authorization model" in _flat(render_help())


def test_help_is_static_and_needs_no_settings():
    assert render_help() == render_help()


# --- the tool counterpart ---------------------------------------------------

def test_describe_configuration_returns_the_same_facts_structured():
    out = _call(_server(POSTURE), "describe_configuration")
    assert out["read_scope"] == "every file"
    assert out["modify_scope"] == "1 listed file(s)"
    assert out["modifiable_file_ids"] == [DOC_ID]
    assert out["capabilities_enabled"] == ["comment.create", "comment.reply"]
    assert "file.trash" in out["capabilities_disabled"]
    assert out["read_only"] is False
    assert out["help_resource"] == HELP_URI


def test_describe_configuration_reports_no_blocked_reason_when_nothing_is_blocked():
    """**Changed with the v0.31.0 defaults.** An unconfigured server blocks nothing, so
    `blocked_reason` must be absent rather than carrying stale text about an unset variable —
    a model reading a reason where there is no refusal will explain a failure that did not
    happen."""
    out = _call(_server({}), "describe_configuration")
    assert not out.get("blocked_reason")
    assert out["capabilities_disabled"] == []


def test_describe_configuration_omits_reasons_too():
    out = _call(_server(POSTURE), "describe_configuration")
    assert "WG lead" not in str(out)


def test_describe_configuration_works_without_credentials():
    """The moment someone asks what this can reach is often the moment nothing works. It must
    not need a token to answer."""
    app = create_server(lambda: (_ for _ in ()).throw(AssertionError("must not be called")),
                        settings=settings_from_env(POSTURE))
    assert _call(app, "describe_configuration")["read_scope"] == "every file"


def test_describe_configuration_is_annotated_read_only():
    tools = {t.name: t for t in asyncio.run(_server(POSTURE).list_tools())}
    assert tools["describe_configuration"].annotations.read_only_hint is True


def test_the_instructions_point_at_it():
    """A resource the model never learns about is a resource nobody reads."""
    from csa_google_workspace.mcp.server import INSTRUCTIONS
    flat = _flat(INSTRUCTIONS)
    assert "describe_configuration" in flat
    assert CONFIG_URI in flat
    assert "Do not retry a refused operation" in flat


# --- not routing around a refusal ------------------------------------------

def test_the_config_resource_says_not_to_route_around_a_refusal():
    """Every control here is enforced in-process. Another Drive integration in the same
    conversation reaches the same account with no allowlist, so a refusal is only a refusal if
    the model does not simply use the other one. That is a hedge that depends on the model
    behaving — the real fix is disabling the other connector, which the README covers — but an
    unstated hedge is strictly worse than a stated one."""
    text = _flat(_read(_server(POSTURE), CONFIG_URI))
    assert "Do not route around it" in text
    assert "another Google Drive integration" in text


def test_the_instructions_say_it_too():
    from csa_google_workspace.mcp.server import INSTRUCTIONS
    flat = _flat(INSTRUCTIONS)
    assert "do not perform it through a different Google Drive integration" in flat


class TestTheCeilingResource:
    """`csa-gw://help/capabilities` — what this server cannot do.

    Written for the model, not for somebody evaluating the tool. The alternative to telling an
    agent that accept-suggestion has no endpoint is letting it discover that by failing, and
    then inventing a workaround: retries, a plausible account of why it "should" work, or a
    detour through another integration to reach the same end. That last one is the expensive
    failure, because it succeeds.
    """

    def text(self):
        from csa_google_workspace.mcp._resources import render_ceiling
        return render_ceiling()

    def test_it_separates_googles_limits_from_ours(self):
        """The two need different responses. A Google limit means stop and say so; one of ours
        means an operator could change it, so the agent should say which."""
        body = self.text()
        assert "Google's limits" in body and "This project's limits" in body

    @pytest.mark.parametrize("subject", [
        "Accept or reject a suggestion",          # no endpoint exists
        "anchored to a specific cell",            # opaque workbook-range id
        "Permanently delete",                     # deliberate, and a security property
        "access settings",                        # meta-permissions, out by choice
        "live formula",                           # removed from this layer in v0.30.13
    ])
    def test_every_known_limit_is_named(self, subject):
        assert subject in self.text(), f"the ceiling does not mention {subject!r}"

    def test_a_limit_that_stops_being_one_is_removed(self):
        """"Revoke or downgrade a permission" was listed as the one gap that was not
        deliberate. #235 closed it in v0.30.14, so it must not still be advertised as
        impossible — a ceiling that names things the server *can* do is worse than one that
        omits things it cannot, because a model believes it and stops."""
        body = self.text()
        assert "Revoke or downgrade" not in body
        assert "taken back only in Drive" not in body

    def test_it_tells_the_agent_not_to_route_around_a_refusal(self):
        """The whole point. Knowing the limit and satisfying the request another way — editing
        the body to simulate accepting a suggestion — is worse than failing."""
        body = self.text()
        assert "not** substitute" in body or "not substitute" in body
        assert "refusal is information" in body

    def test_it_points_at_the_live_policy_for_the_other_question(self):
        """"Cannot" and "not currently permitted" are different, and conflating them turns a
        configuration an operator could widen into an impossibility."""
        from csa_google_workspace.mcp._resources import CONFIG_URI
        assert CONFIG_URI in self.text()

    def test_the_read_tool_can_reach_it(self):
        """Several clients surface resources only to the user, never to the model — which is why
        `read_server_resource` exists. A ceiling the model cannot read is not a ceiling."""
        app = _server(POSTURE)
        out = asyncio.run(app.call_tool("read_server_resource", {"uri": CEILING_URI}))
        assert "cannot do" in str(out)

    def test_the_ceiling_names_uploaded_formats_and_says_it_is_conditional(self):
        """C5, decided 2026-08-30: uploaded-format text extraction is withheld until provenance
        controls exist. The ceiling has to say so, and say it is *conditional* rather than
        impossible — a model that believes a thing is impossible stops, where one that knows it
        is switched off can tell the user what would change it.

        It must also name what DOES work, because metadata and raw bytes work on any file and a
        blanket "not supported" would hide two tools that solve the caller's problem."""
        body = self.text()
        assert ".docx" in body and "PDF" in body
        assert "download_file_content" in body, "the working alternative must be named"
        assert "provenance" in body, "the reason it is withheld, and what would lift it"


class TestTheTwoHelpResourcesAreServedAndNotJustRegistered:
    """A registered resource with a broken body is a link that fails when somebody follows it.

    These two are the ones a model reaches for when it has just been refused - "how do I
    configure this?" and "what can this server not do?" - so an exception here arrives at the
    worst moment, on top of a refusal the reader is already trying to understand.
    """

    def test_the_configuration_reference_is_readable(self):
        text = _flat(_read(_server(POSTURE), HELP_URI))

        assert "CSA_GW_ALLOWLIST_READ" in text
        assert "CSA_GW_CAPABILITIES" in text

    def test_the_ceiling_is_readable_and_separates_the_two_kinds_of_limit(self):
        """Google's limits and this project's. A refusal worth working around and one that is
        not are different situations, and merging them is how somebody spends an afternoon on
        the first kind."""
        text = _flat(_read(_server(POSTURE), CEILING_URI))
        assert "Google" in text

    def test_both_are_listed_with_a_description_that_says_what_they_answer(self):
        """A resource list is a menu. An entry whose description does not say what question it
        answers is one nobody opens."""
        resources = {str(r.uri): r for r in asyncio.run(_server(POSTURE).list_resources())}

        assert HELP_URI in resources and CEILING_URI in resources
        assert "configure" in resources[HELP_URI].description
        assert "impossible" in resources[CEILING_URI].description


class TestDescribingTheCapabilityDefault:
    """The sentence `CSA_GW_CAPABILITIES` gets in the configuration reference, which has two
    forms - and the difference between them is a security claim.

    If the default set EXCLUDES anything, the sentence has to name what. A reader who is told
    only "the default set" and not "which excludes comment.delete" has no way to know whether
    the thing they are about to attempt is on, and the four irreversible capabilities are
    exactly the ones that matter.
    """

    def test_it_names_the_exclusions_when_there_are_any(self, monkeypatch):
        from csa_google_workspace.mcp import _resources

        monkeypatch.setattr(_resources, "DEFAULT_DISABLED", frozenset({"comment.delete"}))
        sentence = _resources._default_note()

        assert "which excludes" in sentence and "`comment.delete`" in sentence

    def test_it_says_so_plainly_when_the_default_excludes_nothing(self, monkeypatch):
        """Today's state, and the one worth being explicit about: unset means EVERYTHING is
        on, including the four Google gives no way to undo. A sentence that merely said "the
        default set" would read as a narrowing."""
        from csa_google_workspace.mcp import _resources

        monkeypatch.setattr(_resources, "DEFAULT_DISABLED", frozenset())
        sentence = _resources._default_note()

        assert "which excludes" not in sentence
        assert "CSA_GW_CAPABILITIES" in sentence

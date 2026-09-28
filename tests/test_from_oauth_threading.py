"""`Workspace.from_oauth` - the interactive constructor, and the one argument it must not drop.

Every other test in this suite replaces this classmethod wholesale, because calling it opens a
browser. So the three lines inside it had never executed, and they carry a claim worth pinning.

`read_only` has to reach BOTH sides:

* `load_credentials`, where it narrows the OAuth SCOPES Google is asked for and picks the
  separate read-only token cache (#185); and
* `from_credentials`, where it sets the client-side posture that refuses writes in software.

Reaching only the first gives a correctly-scoped credential with no local guard. Reaching only
the second is the defect #185 was filed for: a full-Drive token with writes blocked in software,
so any path reaching the credential without passing the Policy gates has full write. Both audits
name a read-only posture as the primary bound on prompt injection, which makes a half-threaded
argument a mitigation that fails open.
"""
from __future__ import annotations

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.policy import PROFILES, Policy


class FakeCredentials:
    """Enough of a credential for `from_credentials` to build services from."""

    valid = True


@pytest.fixture
def captured(monkeypatch):
    """Record what each half was handed, without reaching Google."""
    seen: dict = {}

    monkeypatch.setattr("csa_google_workspace.auth.load_credentials",
                        lambda cs, tp, ro, force=False: seen.update(
                            client_secrets=cs, token_path=tp, read_only=ro, force=force)
                        or FakeCredentials())
    monkeypatch.setattr(Workspace, "from_credentials",
                        classmethod(lambda cls, creds, *, read_only=False, policy=None:
                                    seen.update(built_read_only=read_only, built_policy=policy,
                                                creds=creds) or "a workspace"))
    return seen


def test_read_only_reaches_the_token_and_the_posture(captured):
    assert Workspace.from_oauth("/c.json", "/t.json", read_only=True) == "a workspace"
    assert captured["read_only"] is True, "the credential was not narrowed"
    assert captured["built_read_only"] is True, "the posture was not set"


def test_read_write_is_threaded_just_as_faithfully(captured):
    """The mirror. A `read_only` that was hardcoded True somewhere would pass the test above
    and make every install read-only, which is a different bug with the same one-sided test."""
    Workspace.from_oauth("/c.json", "/t.json")
    assert captured["read_only"] is False and captured["built_read_only"] is False


def test_force_reaches_the_credential_loader_and_not_the_posture(captured):
    """`force` is about consent, not about what the session may do. It belongs on one side
    only, and a `from_credentials` that accepted it would be a second place to get it wrong."""
    Workspace.from_oauth("/c.json", "/t.json", force=True)
    assert captured["force"] is True


def test_a_policy_reaches_the_session_and_not_the_login(captured):
    """A Policy is client-side authority over an already-issued credential. Sending it to the
    login would be meaningless - Google has no idea what `comment.delete` is."""
    policy = Policy(enabled=PROFILES["reader"])
    Workspace.from_oauth("/c.json", "/t.json", policy=policy)

    assert captured["built_policy"] is policy
    assert "policy" not in captured, "the credential loader was handed a policy"


def test_the_paths_are_passed_through_unchanged(captured):
    """Neither expanded nor defaulted here. `load_credentials` owns that, and a second
    expansion in a second place is how two callers come to disagree about which file they
    read - which is exactly what #490 was."""
    Workspace.from_oauth("~/secrets/client.json", "~/tokens/t.json")
    assert captured["client_secrets"] == "~/secrets/client.json"
    assert captured["token_path"] == "~/tokens/t.json"

"""repr() of the domain models must not leak document text or author email into logs
(audit #27 / #49). Multi-tenant servers acting on users' behalf log these objects; the
default dataclass repr would dump other users' content and contact info.
"""
import ast
import pathlib

from csa_google_workspace.comments import Author, Comment, Reply
from csa_google_workspace.suggestions import Suggestion

RAW = {
    "id": "c1",
    "content": "SECRET salary figures",
    "quotedFileContent": {"value": "QUOTED confidential"},
    "author": {"displayName": "Jane Doe", "emailAddress": "jane@corp.example"},
    "replies": [{"id": "r1", "content": "PRIVATE reply note",
                 "author": {"emailAddress": "bob@corp.example"}}],
}


def test_author_repr_omits_email_keeps_name():
    r = repr(Author(display_name="Jane Doe", email="jane@corp.example", is_me=False, photo_url="http://p"))
    assert "jane@corp.example" not in r
    assert "http://p" not in r
    assert "Jane Doe" in r


def test_comment_repr_omits_content_quoted_and_email():
    r = repr(Comment.from_api(RAW))
    for leak in ("SECRET salary figures", "QUOTED confidential", "jane@corp.example"):
        assert leak not in r, f"repr leaked {leak!r}: {r}"
    assert "c1" in r and "content_chars=" in r


def test_reply_repr_omits_content():
    r = repr(Reply.from_api(RAW["replies"][0]))
    assert "PRIVATE reply note" not in r
    assert "r1" in r


def test_suggestion_repr_omits_text():
    r = repr(Suggestion(suggestion_id="s1", kind="insertion", text="CONFIDENTIAL draft"))
    assert "CONFIDENTIAL draft" not in r
    assert "s1" in r


# ---------------------------------------------------------------------------------------
# Fail closed, so the NEXT model cannot slip through.
#
# Everything above is a hand-maintained list, and a hand-maintained list of things that must
# be checked is exactly the shape that goes stale: `AccessProposal` was added with a redacting
# `__repr__` and every test here still passed when that `__repr__` was deleted, because none of
# them had heard of it. `Permission` had been missing for longer.
#
# So this reflects over the package instead, the way `tests/test_policy.py` reflects over
# `Backend`: every `@dataclass` either writes its own `__repr__` or is named below with a
# reason. Adding a model then forces the decision rather than defaulting to "generated".
#
# Read statically with `ast` rather than by importing: `pkgutil.walk_packages` over this
# package HANGS, because importing every module runs things that were never meant to run at
# import time. A guard that has to import the world is a guard that stops being run.

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "csa_google_workspace"

# A generated `__repr__` is fine ONLY when the class cannot carry document text, comment text,
# an email address, or anything else that came from a user. The reason is the point of the
# entry - it is what a reviewer checks, and what dates when the class grows a new field.
GENERATED_REPR_IS_SAFE = {
    "_apply.py::RowResult":      "row number, thread id, booleans - no cell contents",
    "_apply.py::Report":         "counts and RowResults; same",
    "_environment.py::Environment": "which client/token/paths are configured, never their contents",
    "access_proposals.py::RoleAndView": "two role strings from Drive's fixed vocabulary",
    "comments.py::Location":     "cell reference and row/col integers, not the cell's value",
    # Eight tri-state booleans and nothing else: what Drive permits, never what it contains.
    # `ProtectedRange` and `SharedDrive` in the same module DO redact by hand, because a range
    # description is author-written text, an editor list is collaborator PII, and a drive name
    # identifies an organisational unit.
    "restrictions.py::FileRestrictions": "tri-state booleans about permission, no content",
    # A bool and a tuple of PreviewedEntry, each of which redacts its own repr - so the
    # generated one here recurses into redacted output rather than around it.
    "allowlist.py::Preview":     "a bool plus already-redacting PreviewedEntry values",
    "demo/_plan.py::Step":       "the demo's own scripted steps, authored in this repository",
    "demo/_plan.py::Outcome":    "same",
    "demo/_plan.py::Report":     "same",
    "mcp/_auth_flow.py::Loopback": "host and port of the local listener",
    "mcp/_config.py::Settings":  "configuration, and the policy it holds redacts its own",
    "mcp/_desktop.py::Result":   "which config file was written, not what a document said",
    "policy.py::Scope":          "capability names",
    "policy.py::Gate":           "capability name and access kind",
    "policy.py::Policy":         "capability names and allowlist shape",
}


def _dataclasses_in_package():
    """(relative path, class name, writes its own __repr__) for every @dataclass in src/."""
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            decorated = any(
                (isinstance(d, ast.Name) and d.id == "dataclass")
                or (isinstance(d, ast.Attribute) and d.attr == "dataclass")
                or (isinstance(d, ast.Call) and (
                    (isinstance(d.func, ast.Name) and d.func.id == "dataclass")
                    or (isinstance(d.func, ast.Attribute) and d.func.attr == "dataclass")))
                for d in node.decorator_list)
            if not decorated:
                continue
            hand_written = any(isinstance(b, ast.FunctionDef) and b.name == "__repr__"
                               for b in node.body)
            # POSIX separator ALWAYS. `relative_to` yields a WindowsPath whose str is
            # `demo\_plan.py`, so on Windows every id missed the hand-written safe-list above and
            # the guard reported both "every class is undeclared" AND "the safe-list names classes
            # that no longer exist" - simultaneously, which is the tell. Not silent, but the guard
            # certified nothing on that platform. (#453)
            yield f"{path.relative_to(SRC).as_posix()}::{node.name}", hand_written


def test_every_dataclass_either_redacts_or_is_declared_safe():
    """A new model with a generated `__repr__` fails here until somebody says why that is ok."""
    undeclared = sorted(key for key, hand in _dataclasses_in_package()
                        if not hand and key not in GENERATED_REPR_IS_SAFE)
    assert not undeclared, (
        f"these dataclasses use the generated __repr__ and are not declared safe: "
        f"{undeclared}. Either write a redacting __repr__ (see Comment/Author) or add the "
        f"class to GENERATED_REPR_IS_SAFE with a reason it cannot carry user data.")


def test_the_safe_list_does_not_name_classes_that_are_gone():
    """A stale exemption is worse than none: it reads as a considered decision about code that
    no longer exists, and it silently covers a NEW class that reuses the name."""
    present = {key for key, _ in _dataclasses_in_package()}
    stale = sorted(set(GENERATED_REPR_IS_SAFE) - present)
    assert not stale, f"GENERATED_REPR_IS_SAFE names classes that no longer exist: {stale}"


def test_the_safe_list_does_not_cover_a_class_that_redacts_anyway():
    """If a class grew a hand-written `__repr__`, its exemption is now misleading - it suggests
    nobody thought redaction was needed, when somebody did."""
    hand = {key for key, is_hand in _dataclasses_in_package() if is_hand}
    both = sorted(hand & set(GENERATED_REPR_IS_SAFE))
    assert not both, f"these write their own __repr__, so drop the exemption: {both}"


def test_the_models_that_carry_user_data_are_covered_by_name():
    """The reflective check above proves each model DECIDED; these are the ones where the
    decision must be "redact", asserted by name so a future edit cannot quietly exempt one."""
    hand = {key for key, is_hand in _dataclasses_in_package() if is_hand}
    for required in ("comments.py::Comment", "comments.py::Author", "comments.py::Reply",
                     "permissions.py::Permission", "suggestions.py::Suggestion",
                     "access_proposals.py::AccessProposal", "files.py::FileRef"):
        assert required in hand, f"{required} must write a redacting __repr__"

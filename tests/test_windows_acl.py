"""The Windows ACL hardening — the assertions, held until a Windows runner exists.

`auth.py`'s `_harden`, `_read_acl`, `_strays`, `_unexpected_principals`,
`_current_windows_principal` and `_windows_owner_only` are gated on `os.name == "nt"` and CI is
ubuntu-only, so none of them executes here. They carry `# pragma: no cover` naming this file.

**These are NOT A TEST YET stubs**, in the sense `TESTING.md` defines: the exception is that they
*cannot run here*, not that they should not exist. The bodies are written out so that whoever adds
`windows-latest` to the matrix deletes a decorator rather than working out what to assert — which
is the part that otherwise does not get done.

Why this matters more here than elsewhere: #452 found that T5's mitigation evidence was POSIX-only
— `os.chmod` honours the read-only bit and nothing else on Windows, and `O_NOFOLLOW` is absent, so
all three named mechanisms were no-ops. The `icacls` path below is the replacement, and it has
never been executed by an automated test on the platform it exists for.

Unblocked by: adding `windows-latest` to `.github/workflows/tests.yml` (#453). Deferred to 1.0.0
deliberately — Windows runners cost, and the code is exercised locally in the meantime.
"""
import pytest

pytestmark = pytest.mark.skip(
    reason="NOT A TEST YET: Windows-only; CI is ubuntu. Unblocked by adding windows-latest "
           "to the matrix (#453), deferred to 1.0.0."
)


def test_harden_leaves_exactly_one_ace_on_the_token_file(tmp_path):
    """`_harden` must drop the inherited ACL AND remove whatever else is explicitly there.

    `/inheritance:r` drops only INHERITED aces and `/grant:r` replaces only the ace for the
    principal named, so anything explicit Windows itself put on the file survives both - which
    is the gap the extra removal step exists to close.
    """
    from csa_google_workspace import auth

    token = tmp_path / "token.json"
    token.write_text("{}", encoding="utf-8")
    auth._harden(str(token))

    principals, inherited = auth._read_acl(str(token))
    assert inherited is False, "the inherited ACL must be dropped"
    assert auth._strays(principals) == [], f"stray principals survived hardening: {principals}"


def test_file_is_owner_only_reports_unknown_rather_than_secure(tmp_path):
    """Three states, and `None` never means secure.

    An unreadable ACL, an ACL that is the directory's rather than this file's, and an `icacls`
    that said nothing parseable are all *unknown*. Reporting any of them as `True` would claim a
    protection nobody verified.
    """
    from csa_google_workspace import auth

    absent = tmp_path / "nope.json"
    assert auth.file_is_owner_only(str(absent)) is None

    token = tmp_path / "token.json"
    token.write_text("{}", encoding="utf-8")
    auth._harden(str(token))
    assert auth.file_is_owner_only(str(token)) is True


def test_strays_ignores_the_root_equivalents(tmp_path):
    """SYSTEM and BUILTIN\\Administrators are on essentially every file and cannot be removed;
    treating them as strays would make every hardened file report as compromised."""
    from csa_google_workspace import auth

    assert auth._strays(list(auth._WINDOWS_ROOT_EQUIVALENTS)) == []
    assert auth._strays(["CONTOSO\\someoneelse"]) == ["CONTOSO\\someoneelse"]


def test_unexpected_principals_is_empty_after_hardening(tmp_path):
    """The reporting half of the same property, used by the diagnostic surfaces rather than by
    the hardening itself - so it has to agree with `_harden`, not merely be plausible."""
    from csa_google_workspace import auth

    token = tmp_path / "token.json"
    token.write_text("{}", encoding="utf-8")
    auth._harden(str(token))
    assert auth._unexpected_principals(str(token)) == []

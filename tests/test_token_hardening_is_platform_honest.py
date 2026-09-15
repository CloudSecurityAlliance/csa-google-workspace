"""The token file's hardening must be REAL on the platform it runs on, not just on POSIX.

`_write_token` hardens the OAuth refresh token three ways, and on Windows **all three were
no-ops**, silently:

    os.chmod(token_dir, 0o700)                      # Windows honours only the read-only bit
    os.open(..., getattr(os, "O_NOFOLLOW", 0))      # O_NOFOLLOW does not exist -> the flag is 0
    os.fchmod(fd, 0o600)                            # mode stays 0o666

Measured 2026-09-15 on Windows 11 / CPython 3.14: a file created with `os.open(..., 0o600)` and
then `chmod(0o600)` reports `0o666`, and `os.O_NOFOLLOW` is absent from the `os` module.

This is not a cosmetic difference. `THREAT_MODEL.md` T5 - theft of the on-disk token yields
persistent, self-sufficient, full-Drive access - is rated `partially_mitigated`, and cites those
exact three mechanisms as the mitigation. On Windows the evidence for that rating did not hold,
and nothing said so. CI is `ubuntu-latest` only, so nothing could have caught it, while the
product's main deployment target is Claude Desktop/Code - which a great many people run on
Windows.

What protects the file on Windows today is NTFS inheritance from the user profile, which is
real but is not ours: it is whatever ACL happens to be on the directory. `CSA_GW_TOKEN` can
point anywhere, and outside the profile there is nothing. So the fix is to apply an explicit
owner-only ACL rather than to assume the location is kind.

These tests are deliberately written against a platform-agnostic QUESTION - "is this file
readable only by its owner?" - rather than against `0o600`, because `0o600` is the POSIX
*answer* and asserting an answer is how the gap survived.
"""
import errno
import os

import pytest

from csa_google_workspace import auth


class FakeCreds:
    def to_json(self):
        return '{"token": "fake"}'


def test_a_written_token_is_owner_only(tmp_path):
    """The whole point, asked in a way both platforms can answer."""
    token = tmp_path / "token.json"
    auth._write_token(str(token), FakeCreds())
    assert auth.file_is_owner_only(str(token)) is True, (
        "the token is readable by principals other than its owner")


def test_a_pre_existing_loose_file_is_tightened(tmp_path):
    """#17's second facet: O_TRUNC keeps a pre-existing file's permissions, so hardening has to
    happen after the open rather than only in the creation mode."""
    token = tmp_path / "token.json"
    token.write_text("old")
    if os.name != "nt":
        token.chmod(0o644)
    auth._write_token(str(token), FakeCreds())
    assert auth.file_is_owner_only(str(token)) is True


def test_file_is_owner_only_can_tell_a_loose_file_from_a_tight_one(tmp_path):
    """A predicate that answered True unconditionally would pass every test above it. This is
    the test that makes the others mean something."""
    loose = tmp_path / "loose.json"
    loose.write_text("{}")
    if os.name == "nt":
        import subprocess  # nosec B404 - fixed argv, no shell, path we created
        subprocess.run(["icacls", str(loose), "/inheritance:e",
                        "/grant", "Everyone:R"], capture_output=True, check=False)
    else:
        loose.chmod(0o644)
    assert auth.file_is_owner_only(str(loose)) is False


def test_file_is_owner_only_says_it_does_not_know_rather_than_guessing(tmp_path):
    """None is not False. A missing file cannot be reported as "not owner-only", because a
    caller acting on False would tighten something that is not there - and reporting unknown as
    secure is the dangerous direction, so it must not be True either."""
    assert auth.file_is_owner_only(str(tmp_path / "absent.json")) is None


def test_a_symlink_at_the_token_path_is_refused_even_without_O_NOFOLLOW(tmp_path, monkeypatch):
    """The symlink/TOCTOU refusal (#17) is `getattr(os, "O_NOFOLLOW", 0)` - which on Windows is
    literally `| 0`, i.e. the defence is absent and the code reads as though it is present.

    Simulated rather than platform-gated, because creating a symlink on Windows needs Developer
    Mode or elevation (`WinError 1314`), so the real thing cannot be relied on in a test - and a
    test that skips on the platform with the bug is not a test.
    """
    monkeypatch.setattr(auth.os, "O_NOFOLLOW", 0, raising=False)
    monkeypatch.setattr(auth.os.path, "islink", lambda p: True)
    with pytest.raises(OSError) as e:
        auth._write_token(str(tmp_path / "token.json"), FakeCreds())
    assert e.value.errno == errno.ELOOP


def test_the_real_symlink_refusal_still_works_where_symlinks_can_be_made(tmp_path):
    """The explicit check must not have REPLACED O_NOFOLLOW where O_NOFOLLOW exists - it is a
    fallback, and the kernel check is the atomic one."""
    link = tmp_path / "token.json"
    try:
        link.symlink_to(tmp_path / "nonexistent-target.json")
    except (OSError, NotImplementedError):
        pytest.skip("this platform will not create a symlink without elevation")
    with pytest.raises(OSError):
        auth._write_token(str(link), FakeCreds())


def test_the_parent_directory_we_create_is_owner_only(tmp_path):
    token = tmp_path / "made-by-us" / "token.json"
    auth._write_token(str(token), FakeCreds())
    assert auth.file_is_owner_only(str(token.parent)) is True


def test_the_parent_directory_we_create_is_still_traversable(tmp_path):
    """A directory needs the execute bit, and `file_is_owner_only` cannot tell you that.

    `0o600` and `0o700` both satisfy "no access for group or other", so the predicate above
    answers True for a directory nothing can enter - including us, on the very next call. This
    is the second half of that property and it is a SEPARATE question, which is why it is a
    separate test rather than another assertion.

    It can only fail on POSIX. On Windows there is no execute bit to lose, so a Windows-only run
    cannot reach the bug at all - which is the argument for the CI leg, not against the test.
    """
    token = tmp_path / "made-by-us" / "token.json"
    auth._write_token(str(token), FakeCreds())
    auth._write_token(str(token), FakeCreds())          # must be able to re-enter the directory
    assert os.listdir(str(token.parent)) == ["token.json"]
    assert (token).read_text() == '{"token": "fake"}'


def test_a_caller_supplied_directory_is_not_mutated(tmp_path):
    """#4: hardening a directory the caller already had is a side effect nobody asked for, and
    that stays true on Windows - an explicit ACL is a bigger mutation than a chmod, not a
    smaller one."""
    d = tmp_path / "caller-dir"
    d.mkdir()
    before = auth.file_is_owner_only(str(d))
    auth._write_token(str(d / "token.json"), FakeCreds())
    assert auth.file_is_owner_only(str(d)) == before

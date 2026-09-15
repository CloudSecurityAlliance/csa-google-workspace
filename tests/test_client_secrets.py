"""Reading the OAuth client-secrets file: tolerate a BOM, and fail ACTIONABLY (#449).

Two defects motivated this file, and the second is the expensive one.

**A UTF-8 BOM made a valid file unreadable.** `google_auth_oauthlib` opens the file with no
`encoding=` argument, so U+FEFF lands at char 0 and `json.load` refuses it. A BOM is legal in a
UTF-8 file and plenty of Windows tooling emits one - `Set-Content -Encoding utf8` does under
Windows PowerShell 5.1 but not under PowerShell 7, which is how one arrived here. Any future
writer can reintroduce it, so the client is what has to be tolerant.

**The error named neither the file nor what was being read.** `Expecting value: line 1 column 1
(char 0)`, pointing at a line inside a dependency, is not something a user can act on. That is
what turned a one-byte problem into a multi-step investigation, and it is the half that stays
valuable when the file genuinely IS malformed.

The third site is the interesting one. `_login._client_id_of` catches `(OSError, ValueError)`
and `JSONDecodeError` SUBCLASSES `ValueError`, so a BOM did not crash there - it returned None
and silently disabled the "this cached token came from a different OAuth client" warning. A
guard written to mean "file missing or not our shape" was quietly recruited into suppressing a
security warning, which is CLAUDE.md invariant 11 arriving from below.
"""
import json

import pytest

from csa_google_workspace import auth
from csa_google_workspace.exceptions import AuthError

INSTALLED = {
    "installed": {
        "client_id": "abc.apps.googleusercontent.com",
        "client_secret": "not-a-real-secret",           # nosec B105 - fixture
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}


def _write(path, payload, encoding="utf-8"):
    path.write_text(json.dumps(payload), encoding=encoding)
    return str(path)


def test_a_utf8_bom_does_not_make_a_valid_file_unreadable(tmp_path):
    """The reported defect. `utf-8-sig` strips a BOM and is a no-op without one."""
    p = _write(tmp_path / "client_secret.json", INSTALLED, encoding="utf-8-sig")
    assert open(p, "rb").read(3) == b"\xef\xbb\xbf", "fixture must actually carry a BOM"
    assert auth.read_client_secrets(p) == INSTALLED


def test_a_plain_utf8_file_still_reads(tmp_path):
    p = _write(tmp_path / "client_secret.json", INSTALLED)
    assert auth.read_client_secrets(p) == INSTALLED


def test_a_missing_file_names_the_path_it_looked_at(tmp_path):
    missing = str(tmp_path / "nope.json")
    with pytest.raises(AuthError) as e:
        auth.read_client_secrets(missing)
    assert missing in str(e.value)


def test_malformed_json_names_the_path_and_says_what_it_was_reading(tmp_path):
    """The unactionable-error half. A user seeing this must learn three things they could not
    learn from `Expecting value: line 1 column 1 (char 0)`: which file, what that file is for,
    and that the underlying complaint was a JSON parse."""
    p = tmp_path / "client_secret.json"
    p.write_text("{ not json", encoding="utf-8")
    with pytest.raises(AuthError) as e:
        auth.read_client_secrets(str(p))
    msg = str(e.value)
    assert str(p) in msg, "must name the file"
    assert "OAuth client secrets" in msg, "must say what the file is"
    assert "line 1" in msg, "must keep the underlying parse detail, not discard it"


def test_a_json_file_of_the_wrong_shape_is_refused_by_name(tmp_path):
    """Valid JSON, wrong document. The common form is handing us a service-account key or a
    Web-application client instead of a Desktop-app one, and the message has to say so - the
    upstream 'Client secrets must be for a web or installed app' names no file."""
    p = _write(tmp_path / "client_secret.json", {"type": "service_account"})
    with pytest.raises(AuthError) as e:
        auth.read_client_secrets(str(p))
    msg = str(e.value)
    assert str(p) in msg
    assert "installed" in msg or "Desktop" in msg


def test_a_directory_in_place_of_the_file_is_an_auth_error(tmp_path):
    """An OSError that is not FileNotFoundError still has to arrive as an AuthError naming the
    path, rather than as an IsADirectoryError/PermissionError from inside `open`."""
    with pytest.raises(AuthError) as e:
        auth.read_client_secrets(str(tmp_path))
    assert str(tmp_path) in str(e.value)


def test_the_wrong_oauth_client_warning_survives_a_bom(tmp_path):
    """The silent half of #449, and the reason this is more than an ergonomics fix.

    `_client_id_of` returns None for an unreadable file, and `login` only warns that a cached
    token came from a different OAuth client when it can read BOTH ids. A BOM made the file
    unreadable, so the warning could not fire - a security check disabled by a byte order mark.
    """
    from csa_google_workspace.mcp._login import _client_id_of
    p = _write(tmp_path / "client_secret.json", INSTALLED, encoding="utf-8-sig")
    assert _client_id_of(p) == "abc.apps.googleusercontent.com"


def test_client_id_of_still_returns_none_for_a_genuinely_unreadable_file(tmp_path):
    """The tolerance must not turn into "never reports a problem". Its contract is None-on-
    unreadable and that still holds; only the definition of unreadable narrowed."""
    from csa_google_workspace.mcp._login import _client_id_of
    p = tmp_path / "client_secret.json"
    p.write_text("{ not json", encoding="utf-8")
    assert _client_id_of(str(p)) is None
    assert _client_id_of(str(tmp_path / "absent.json")) is None


def test_the_mcp_browser_flow_also_tolerates_a_bom(tmp_path):
    """The third reader. `authenticate` builds its Flow through a different call than `login`,
    so fixing only `auth.py` would leave the MCP path failing identically."""
    from csa_google_workspace.mcp._auth_flow import build_flow
    p = _write(tmp_path / "client_secret.json", INSTALLED, encoding="utf-8-sig")
    flow = build_flow(p, read_only=False, redirect_uri="http://localhost:1/oauth2callback")
    assert flow.client_config["client_id"] == "abc.apps.googleusercontent.com"

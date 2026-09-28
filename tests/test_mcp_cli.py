"""Entry-point guards (spec §5.1, §9).

These are the tests that would have caught the *original* design, in which `main()` called
`from_oauth` and so could reach `InstalledAppFlow.run_local_server()` — which `print()`s the
consent URL to stdout and blocks on a browser redirect. Under stdio, stdout carries JSON-RPC,
so that corrupts the protocol stream before the session even starts.

Asserting the error text alone would not be enough: it would still pass if consent ran first
and merely failed afterwards. The invariant is the *absence* of the interactive flow, so that
is what is asserted.
"""
import contextlib
import io
import pathlib

import pytest

from csa_google_workspace import auth
from csa_google_workspace.mcp import cli


class Ran(Exception):
    """Raised in place of actually serving stdio."""


def _no_flow(*args, **kwargs):
    raise AssertionError("the stdio server must never construct the interactive OAuth flow")


@pytest.fixture
def no_interactive_flow(monkeypatch):
    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_secrets_file", _no_flow)


@pytest.fixture
def captured_server(monkeypatch):
    """Replace MCPServer.run so the server 'starts' without occupying stdio."""
    started = {}

    def fake_run(self, transport="stdio", **kwargs):
        started["transport"] = transport
        raise Ran
    monkeypatch.setattr("mcp.server.MCPServer.run", fake_run)
    return started


# --- the server never prompts ------------------------------------------------

def test_server_starts_with_no_token_and_never_prompts(tmp_path, no_interactive_flow, captured_server):
    """A missing token must NOT stop the server starting: an MCP client renders a startup
    crash as an opaque failure, so the remedy has to reach the user as a tool error instead."""
    env = {"CSA_GW_TOKEN": str(tmp_path / "absent.json")}
    with pytest.raises(Ran):
        cli.main([], env)
    assert captured_server["transport"] == "stdio"


def test_server_startup_writes_nothing_to_stdout(tmp_path, no_interactive_flow, captured_server):
    """stdout is the JSON-RPC channel. One stray print corrupts the stream."""
    env = {"CSA_GW_TOKEN": str(tmp_path / "absent.json")}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), pytest.raises(Ran):
        cli.main([], env)
    assert buf.getvalue() == ""


def test_help_goes_to_stderr_not_stdout(capsys):
    assert cli.main(["--help"], {}) == 0
    out, err = capsys.readouterr()
    assert out == "" and "usage:" in err


def test_version_prints_the_installed_version(capsys):
    """`--version` answers "what is on this machine?" without starting a session.

    On stderr like every other CLI output here: stdout is the JSON-RPC channel, and one
    stray byte on it corrupts the session.
    """
    from csa_google_workspace import __version__

    assert cli.main(["--version"], {}) == 0
    captured = capsys.readouterr()
    assert captured.out == ""                      # stdout stays clean
    assert captured.err.strip() == __version__


def test_usage_text_is_ascii_only() -> None:
    """The usage text reaches Windows consoles, where cp437/cp1252 mangles anything else.

    Measured: an em dash in this string printed as a u-grave on a real Windows 5.1 console.
    """
    offenders = sorted({c for c in cli.USAGE if ord(c) > 127})
    assert offenders == [], f"non-ASCII in USAGE: {offenders}"


def test_unknown_argument_is_rejected_on_stderr(capsys):
    assert cli.main(["frobnicate"], {}) == 2
    out, err = capsys.readouterr()
    assert out == "" and "unknown argument" in err


# --- login is the only interactive path --------------------------------------

def test_login_without_client_secrets_reports_the_missing_variable(tmp_path, monkeypatch, capsys):
    # Must patch the default path: otherwise this passes or fails depending on whether the
    # developer happens to have ~/.csa_google_workspace/client_secret.json — green in CI,
    # red on a machine that has actually used the tool.
    monkeypatch.setattr("csa_google_workspace.mcp._login.DEFAULT_CLIENT_SECRETS_PATH",
                        str(tmp_path / "absent.json"))
    assert cli.main(["login"], {}) == 2
    assert "CSA_GW_CLIENT_SECRETS" in capsys.readouterr().err


def test_login_runs_the_interactive_flow(tmp_path, monkeypatch, capsys):
    """The mirror image: `login` *must* reach from_oauth, since that is its whole job."""
    called = {}

    def fake_from_oauth(client_secrets, token_path, read_only=False, force=False):
        called["args"] = (client_secrets, token_path, read_only)
    monkeypatch.setattr("csa_google_workspace.workspace.Workspace.from_oauth", fake_from_oauth)

    env = {"CSA_GW_CLIENT_SECRETS": "/tmp/cs.json", "CSA_GW_TOKEN": str(tmp_path / "t.json")}
    assert cli.main(["login"], env) == 0
    assert called["args"] == ("/tmp/cs.json", str(tmp_path / "t.json"), False)


def test_read_only_env_reaches_login(tmp_path, monkeypatch):
    called = {}
    monkeypatch.setattr("csa_google_workspace.workspace.Workspace.from_oauth",
                        lambda cs, tp, read_only=False, force=False: called.setdefault("ro", read_only))
    cli.main(["login"], {"CSA_GW_CLIENT_SECRETS": "/tmp/cs.json",
                         "CSA_GW_TOKEN": str(tmp_path / "t.json"), "CSA_GW_READ_ONLY": "1"})
    assert called["ro"] is True


# --- `login --force` and cached-token reporting -------------------------------
#
# Real failure this addresses: a token cache can hold a perfectly valid token that was
# minted by a DIFFERENT OAuth client (same scopes, different project). `login` then
# reuses it and truthfully reports success, while every API call runs against the wrong
# project's quota and consent screen. Nothing errors; it is just silently wrong.

def test_login_reuses_a_usable_token_without_opening_a_browser(tmp_path, monkeypatch, capsys):
    token = tmp_path / "token.json"
    token.write_text('{"client_id": "111-abc.apps.googleusercontent.com"}')
    monkeypatch.setattr("csa_google_workspace.mcp._login._client_id_of",
                        lambda p: "111-abc.apps.googleusercontent.com")
    monkeypatch.setattr("csa_google_workspace.mcp._login.load_cached_credentials",
                        lambda tp, ro: object())
    called = {}
    monkeypatch.setattr("csa_google_workspace.workspace.Workspace.from_oauth",
                        lambda *a, **k: called.setdefault("ran", True))

    env = {"CSA_GW_CLIENT_SECRETS": "/tmp/cs.json", "CSA_GW_TOKEN": str(token)}
    assert cli.main(["login"], env) == 0
    assert "ran" not in called                       # no browser
    assert "already authorized" in capsys.readouterr().out.lower()


def test_login_force_reauthorizes_even_with_a_usable_token(tmp_path, monkeypatch):
    token = tmp_path / "token.json"
    token.write_text("{}")
    monkeypatch.setattr("csa_google_workspace.mcp._login.load_cached_credentials",
                        lambda tp, ro: object())
    called = {}
    monkeypatch.setattr("csa_google_workspace.workspace.Workspace.from_oauth",
                        lambda cs, tp, read_only=False, force=False: called.update(force=force))

    env = {"CSA_GW_CLIENT_SECRETS": "/tmp/cs.json", "CSA_GW_TOKEN": str(token)}
    assert cli.main(["login", "--force"], env) == 0
    assert called["force"] is True                   # cache bypassed, consent re-run


def test_login_warns_when_the_cached_token_is_from_another_client(tmp_path, monkeypatch, capsys):
    """The exact trap: valid token, right scopes, wrong project."""
    token = tmp_path / "token.json"
    token.write_text('{"client_id": "945234811286-old.apps.googleusercontent.com"}')
    monkeypatch.setattr("csa_google_workspace.mcp._login._client_id_of",
                        lambda p: "548573610436-new.apps.googleusercontent.com")
    monkeypatch.setattr("csa_google_workspace.mcp._login.load_cached_credentials",
                        lambda tp, ro: object())
    monkeypatch.setattr("csa_google_workspace.workspace.Workspace.from_oauth",
                        lambda *a, **k: None)

    env = {"CSA_GW_CLIENT_SECRETS": "/tmp/cs.json", "CSA_GW_TOKEN": str(token)}
    assert cli.main(["login"], env) == 0
    err = capsys.readouterr().err.lower()
    assert "different oauth client" in err and "--force" in err


def test_login_with_no_token_authorizes_without_needing_force(tmp_path, monkeypatch):
    token = tmp_path / "absent.json"
    monkeypatch.setattr("csa_google_workspace.mcp._login.load_cached_credentials",
                        lambda tp, ro: (_ for _ in ()).throw(auth.AuthError("no cached credentials")))
    called = {}
    monkeypatch.setattr("csa_google_workspace.workspace.Workspace.from_oauth",
                        lambda cs, tp, read_only=False, force=False: called.update(ran=True))

    env = {"CSA_GW_CLIENT_SECRETS": "/tmp/cs.json", "CSA_GW_TOKEN": str(token)}
    assert cli.main(["login"], env) == 0
    assert called["ran"] is True


def test_force_flag_is_documented_in_usage(capsys):
    cli.main(["--help"], {})
    assert "--force" in capsys.readouterr().err


# --- branded OAuth success page ----------------------------------------------
#
# google_auth_oauthlib hardcodes `Content-type: text/plain` in _RedirectWSGIApp, so the
# public `success_message=` argument cannot carry markup. Swapping the class for the
# duration of the flow is the only seam — and a cosmetic upgrade must never be able to
# break authorization, so the fallback behaviour is tested as carefully as the feature.

def _wsgi_environ(uri="http://127.0.0.1:8080/?code=abc&state=xyz"):
    from urllib.parse import urlsplit
    u = urlsplit(uri)
    return {"wsgi.url_scheme": "http", "HTTP_HOST": u.netloc, "PATH_INFO": u.path,
            "QUERY_STRING": u.query, "SERVER_NAME": "127.0.0.1", "SERVER_PORT": "8080"}


def test_branded_page_is_served_as_html():
    import google_auth_oauthlib.flow as flow

    from csa_google_workspace.mcp._login import _branded_success_page

    with _branded_success_page():
        app = flow._RedirectWSGIApp("ignored")
        captured = {}
        body = app(_wsgi_environ(), lambda status, headers: captured.update(dict(headers)))

    assert "text/html" in captured["Content-type"]
    html = b"".join(body).decode()
    assert "<!doctype html>" in html.lower()
    assert "authorized" in html.lower()


def test_branded_page_still_records_the_redirect_uri():
    """The security-relevant half: last_request_uri carries the auth code and the state
    oauthlib validates. Losing it would break the flow, not just the styling."""
    import google_auth_oauthlib.flow as flow

    from csa_google_workspace.mcp._login import _branded_success_page

    with _branded_success_page():
        app = flow._RedirectWSGIApp("ignored")
        app(_wsgi_environ("http://127.0.0.1:8080/?code=THECODE&state=THESTATE"),
            lambda status, headers: None)

    assert "code=THECODE" in app.last_request_uri
    assert "state=THESTATE" in app.last_request_uri


def test_the_original_class_is_restored_afterwards():
    import google_auth_oauthlib.flow as flow

    from csa_google_workspace.mcp._login import _branded_success_page

    before = flow._RedirectWSGIApp
    with _branded_success_page():
        assert flow._RedirectWSGIApp is not before
    assert flow._RedirectWSGIApp is before


def test_original_class_is_restored_even_when_the_flow_raises():
    import google_auth_oauthlib.flow as flow

    from csa_google_workspace.mcp._login import _branded_success_page

    before = flow._RedirectWSGIApp
    with pytest.raises(RuntimeError):
        with _branded_success_page():
            raise RuntimeError("consent blew up")
    assert flow._RedirectWSGIApp is before


def test_missing_upstream_class_degrades_instead_of_failing(monkeypatch):
    """If upstream renames the private class, login must keep working — plainer, not broken."""
    import google_auth_oauthlib.flow as flow

    from csa_google_workspace.mcp._login import _branded_success_page

    monkeypatch.delattr(flow, "_RedirectWSGIApp")
    with _branded_success_page():
        pass                                    # must not raise


def test_page_embeds_the_logo_and_avoids_the_superseded_orange():
    """Brand: the logo is inlined verbatim (recoloring is forbidden), and the page adds no
    orange of its own — so the asset's older #F98526 never sits beside the current #FF7A00."""
    from csa_google_workspace.mcp._success_page import SUCCESS_HTML

    assert "<svg" in SUCCESS_HTML and "Cloud Security Alliance" in SUCCESS_HTML
    assert "#00549F" in SUCCESS_HTML                      # CSA Blue B500
    assert "#FF7A00" not in SUCCESS_HTML.upper().replace("#F98526", "")


# --- login finds the client secrets without being told -----------------------
#
# The setup script writes the client to ~/.csa_google_workspace/client_secret.json — a
# path this package chose. Requiring an env var to point back at our own convention just
# makes the user rediscover it, which is exactly what happened in practice.

def test_login_uses_the_default_client_secrets_path_when_env_is_unset(tmp_path, monkeypatch):
    secrets = tmp_path / "client_secret.json"
    secrets.write_text("{}")
    monkeypatch.setattr("csa_google_workspace.mcp._login.DEFAULT_CLIENT_SECRETS_PATH", str(secrets))
    monkeypatch.setattr("csa_google_workspace.mcp._login.load_cached_credentials",
                        lambda tp, ro: (_ for _ in ()).throw(auth.AuthError("no cached credentials")))
    called = {}
    monkeypatch.setattr("csa_google_workspace.workspace.Workspace.from_oauth",
                        lambda cs, tp, read_only=False, force=False: called.update(cs=cs))

    assert cli.main(["login"], {"CSA_GW_TOKEN": str(tmp_path / "t.json")}) == 0
    assert called["cs"] == str(secrets)


def test_env_var_still_wins_over_the_default(tmp_path, monkeypatch):
    default = tmp_path / "default.json"; default.write_text("{}")
    explicit = tmp_path / "explicit.json"; explicit.write_text("{}")
    monkeypatch.setattr("csa_google_workspace.mcp._login.DEFAULT_CLIENT_SECRETS_PATH", str(default))
    monkeypatch.setattr("csa_google_workspace.mcp._login.load_cached_credentials",
                        lambda tp, ro: (_ for _ in ()).throw(auth.AuthError("none")))
    called = {}
    monkeypatch.setattr("csa_google_workspace.workspace.Workspace.from_oauth",
                        lambda cs, tp, read_only=False, force=False: called.update(cs=cs))

    cli.main(["login"], {"CSA_GW_CLIENT_SECRETS": str(explicit), "CSA_GW_TOKEN": str(tmp_path / "t.json")})
    assert called["cs"] == str(explicit)


def test_missing_everywhere_says_where_it_looked(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("csa_google_workspace.mcp._login.DEFAULT_CLIENT_SECRETS_PATH",
                        str(tmp_path / "absent.json"))
    assert cli.main(["login"], {}) == 2
    err = capsys.readouterr().err
    assert "CSA_GW_CLIENT_SECRETS" in err and "absent.json" in err


# --- the verbs that answer questions without starting a session ---------------
#
# `describe` and `configure` exist for the same reason `--version` does: an installer could
# not otherwise check what it had just installed, configured, or granted. All three were
# added after a real bug in which the CSA installer printed a notice about the DEFAULT
# posture while the user's actual environment said something else.

def test_describe_prints_the_effective_policy_not_the_default_one(capsys):
    """The RR-003 shape: a notice about permissions has to be GENERATED from the permissions.

    So the env is set to something that is not the default, and the output has to reflect
    it. Asserting only that `describe` prints *something* would pass against a hardcoded
    string, which is the exact defect this verb exists to prevent.
    """
    assert cli.main(["describe"], {"CSA_GW_READ_ONLY": "1"}) == 0
    out, err = capsys.readouterr()
    assert out == ""                                   # stdout is the JSON-RPC channel
    assert "Read-only mode: **on**" in err

    # The same line, from the same renderer, with the environment removed. Both renderings
    # mention read-only mode - only the VALUE differs - so matching on the word alone would
    # pass against either, which is the mistake this pair exists to rule out.
    assert cli.main(["describe"], {}) == 0
    assert "Read-only mode: **off**" in capsys.readouterr().err


def test_describe_accepts_its_aliases(capsys):
    for verb in ("describe", "describe-configuration", "config"):
        assert cli.main([verb], {}) == 0
        assert capsys.readouterr().err != ""


class TestConfigure:
    """`configure` merges this server into Claude Desktop's config file.

    Every test here pins `config_path` at a tmp file. The suite-wide HOME redirect already
    keeps the real one out of reach, but these need to READ BACK what was written, and a
    test that asserts on a path it did not choose is one that stops meaning anything the day
    the default moves.
    """

    @pytest.fixture
    def desktop(self, tmp_path, monkeypatch):
        path = tmp_path / "claude_desktop_config.json"
        monkeypatch.setattr("csa_google_workspace.mcp._desktop.config_path", lambda env=None: path)
        return path

    def test_it_writes_the_config_and_says_where(self, desktop, capsys):
        import json

        assert cli.main(["configure"], {}) == 0
        out, err = capsys.readouterr()
        assert out == ""
        assert f"created {desktop}" in err
        assert "restart Claude Desktop" in err
        assert "csa-google-workspace" in json.loads(desktop.read_text())["mcpServers"]

    def test_print_writes_nothing_at_all(self, desktop, capsys):
        """`--print` is what somebody runs before trusting this with a file that already has
        their other servers in it. It has to be inert, not merely quiet."""
        assert cli.main(["configure", "--print"], {}) == 0
        assert not desktop.exists()
        assert f"would write to {desktop}" in capsys.readouterr().err

    def test_a_second_run_reports_no_change_rather_than_claiming_an_update(self, desktop, capsys):
        cli.main(["configure"], {}); capsys.readouterr()
        assert cli.main(["configure"], {}) == 0
        assert "already correct" in capsys.readouterr().err

    def test_a_changed_entry_is_reported_as_an_update_and_keeps_a_backup(self, desktop, capsys):
        """A backup that does not hold the PREVIOUS version is worse than no backup, because
        somebody trusts it. So the path printed is opened and compared, rather than the line
        merely being present - the failure mode here is a real file with the wrong contents."""
        cli.main(["configure"], {}); capsys.readouterr()
        before = desktop.read_text()

        assert cli.main(["configure"], {"CSA_GW_READ_ONLY": "1"}) == 0
        err = capsys.readouterr().err
        assert f"updated {desktop}" in err

        kept = err.split("previous version kept at ")[1].splitlines()[0]
        assert pathlib.Path(kept).read_text() == before
        assert desktop.read_text() != before

    def test_it_names_the_variables_it_carried(self, desktop, capsys):
        """Desktop has no shell, so the config's `env` block is the only place it reads
        policy from. Naming them is how somebody checks that the posture they set in a
        terminal is the posture Desktop will run under."""
        cli.main(["configure"], {"CSA_GW_READ_ONLY": "1", "CSA_GW_PROFILE": "reader"})
        err = capsys.readouterr().err
        assert "carried 2 CSA_GW_* variable(s)" in err
        assert "CSA_GW_READ_ONLY" in err and "CSA_GW_PROFILE" in err

    def test_carrying_nothing_says_the_defaults_are_OPEN(self, desktop, capsys):
        """RR-003, found 2026-09-01. This printed the OPPOSITE of runtime behaviour at the
        moment somebody set the server up - "nothing is reachable until you set an
        allowlist" when in fact everything is. A wrong sentence in a file nobody opens is a
        defect; a wrong sentence printed during setup is somebody believing they are scoped
        when they are not."""
        cli.main(["configure"], {})
        err = capsys.readouterr().err
        assert "none were carried" in err
        assert "THE DEFAULTS, WHICH ARE OPEN" in err
        assert "CSA_GW_READ_ONLY=1" in err, "it must say how to narrow, not just that it is wide"

    def test_an_unparseable_config_is_refused_rather_than_replaced(self, desktop, capsys):
        """Somebody's other MCP servers live in that file. A file that does not parse is
        most likely one they are part-way through editing, so the cost of guessing wrong is
        their whole config - exit 1 and touch nothing."""
        desktop.write_text('{"mcpServers": {', encoding="utf-8")
        assert cli.main(["configure"], {}) == 1
        assert desktop.read_text() == '{"mcpServers": {', "the file was modified"
        assert "not valid JSON" in capsys.readouterr().err

    def test_an_unknown_argument_is_rejected_with_usage(self, desktop, capsys):
        assert cli.main(["configure", "--frobnicate"], {}) == 2
        assert not desktop.exists()
        err = capsys.readouterr().err
        assert "unknown argument: --frobnicate" in err and "usage:" in err

    def test_it_accepts_the_other_two_spellings_of_print(self, desktop, capsys):
        for flag in ("--dry-run", "-n"):
            assert cli.main(["configure", flag], {}) == 0
            assert not desktop.exists()
            assert "would write to" in capsys.readouterr().err


def test_login_rejects_an_unknown_flag_instead_of_treating_it_as_force(capsys):
    """`login --frce` must not silently become a plain login - and must certainly not become
    `--force`, which throws away a working token and reopens a browser."""
    assert cli.main(["login", "--frce"], {}) == 2
    err = capsys.readouterr().err
    assert "unknown argument: --frce" in err and "usage:" in err


def test_demo_is_dispatched_with_the_remaining_arguments(monkeypatch):
    """The demo is this project's end-to-end test, and it is imported inside the branch so
    the server path never loads it. What is asserted is the hand-off: the verb is consumed
    and everything after it reaches the demo untouched."""
    seen = {}
    monkeypatch.setattr("csa_google_workspace.demo._cli.main",
                        lambda argv, env: seen.update(argv=argv, env=env) or 7)

    assert cli.main(["demo", "--auto"], {"CSA_GW_TOKEN": "/t"}) == 7
    assert seen["argv"] == ["--auto"]
    assert seen["env"] == {"CSA_GW_TOKEN": "/t"}


def test_a_clean_shutdown_exits_zero(tmp_path, no_interactive_flow, monkeypatch):
    """`run()` returning is the normal end of a session: the client closed stdio. Exiting
    non-zero there would report a crash on every ordinary disconnect, and the place that
    reads the exit code is whatever supervises the server - a launcher, a wrapper script, a
    log somebody scans for failures.

    Every other test here makes `run` raise, so the line after it had never executed.
    """
    ran = {}
    monkeypatch.setattr("mcp.server.MCPServer.run",
                        lambda self, transport="stdio", **kw: ran.update(transport=transport))

    assert cli.main([], {"CSA_GW_TOKEN": str(tmp_path / "absent.json")}) == 0
    assert ran == {"transport": "stdio"}

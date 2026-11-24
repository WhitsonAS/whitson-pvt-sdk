import json
import subprocess
import sys
import webbrowser

import httpx2
import pytest
from typer.testing import CliRunner

from tests.conftest import DISCOVERY, ISSUER, TOKEN_ENDPOINT, auth_config, form
from whitson_pvt_sdk._store import ActiveLogin
from whitson_pvt_sdk.cli._app import app
from whitson_pvt_sdk.cli._auth import _open_browser

REVOKE = f"{ISSUER}oauth/revoke"
IDENTITY = {
    "kind": "user_token",
    "user_id": 7,
    "name": "Ada Lovelace",
    "email": "ada@example.com",
    "role": "project_editor",
    "scopes": ["read:data"],
    "client_id": "cli-client",
}
API_TOKEN_IDENTITY = {
    "kind": "api_token",
    "user_id": 7,
    "name": None,
    "email": "ada@example.com",
    "role": "reader",
    "scopes": ["read:data"],
    "token_id": 12,
    "token_name": "nightly export",
}
LEGACY_IDENTITY = {"kind": "legacy_client", "client_subject": "abc@clients", "full_access": True}
ME = {**IDENTITY, "added_later": {"ignored": True}}
SECRETS = ("stored-access", "stored-refresh", "env-token")

runner = CliRunner()


def _no_secrets(result) -> None:
    for secret in SECRETS:
        assert secret not in result.stdout
        assert secret not in result.stderr


@pytest.mark.parametrize(
    ("use_env_token", "credential", "identity"),
    [
        (False, {"kind": "stored_login", "source": "store"}, IDENTITY),
        (True, {"kind": "api_token", "source": "environment"}, API_TOKEN_IDENTITY),
        (True, {"kind": "api_token", "source": "environment"}, LEGACY_IDENTITY),
    ],
    ids=["stored-login", "env-token", "legacy-client"],
)
def test_status_reports_the_credential_and_identity(
    base_url, httpx2_mock, monkeypatch, store_login, use_env_token, credential, identity
):
    store_login(base_url, access="stored-access", refresh="stored-refresh")
    if use_env_token:
        monkeypatch.setenv("WHITSON_PVT_TOKEN", "env-token")
        monkeypatch.setenv("WHITSON_PVT_URL", base_url)
    httpx2_mock.add_response(
        url=f"{base_url}/external/v2/me",
        json={**identity, "added_later": {"ignored": True}},
        is_reusable=True,
    )

    result = runner.invoke(app, ["auth", "status", "--json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == {
        "url": base_url,
        "credential": credential,
        "identity": identity,
    }
    _no_secrets(result)

    text = runner.invoke(app, ["auth", "status"])
    assert text.exit_code == 0
    _no_secrets(text)


ROLE_NOT_CONFIRMED = (
    "Your whitsonPVT role has not been confirmed in the last 30 days; sign in to the whitsonPVT "
    "web app, then try again"
)


@pytest.mark.parametrize(
    ("setup", "exit_code", "kind", "message", "absent"),
    [
        ("nothing", 2, "configuration", "wpvt auth login --url", None),
        ("invalid-login", 3, "authentication", "no longer valid", None),
        (
            "refused-login",
            3,
            "authentication",
            f"rejected the credential: {ROLE_NOT_CONFIRMED}.",
            "wpvt auth login",
        ),
        ("refused-login-without-reason", 3, "authentication", "wpvt auth login --url", None),
        ("rejected-token", 3, "authentication", "Check the token in WHITSON_PVT_TOKEN", None),
        ("unreachable", 4, "network", "Request failed", None),
    ],
)
@pytest.mark.usefixtures("no_retry_sleep")
def test_status_failures_have_distinct_exit_codes(
    base_url, httpx2_mock, monkeypatch, store, store_login, setup, exit_code, kind, message, absent
):
    monkeypatch.setenv("WHITSON_PVT_URL", base_url)
    me = f"{base_url}/external/v2/me"
    match setup:
        case "invalid-login":
            store_login(base_url, access="stored-access", refresh="stored-refresh")
            with store.transaction() as transaction:
                transaction.mark_invalid(base_url, "the refresh token was revoked")
        case "refused-login" | "refused-login-without-reason":
            store_login(base_url, access="stored-access", refresh="stored-refresh")
            httpx2_mock.add_response(
                method="POST",
                url=TOKEN_ENDPOINT,
                json={"access_token": "renewed-access", "token_type": "Bearer", "expires_in": 3600},
            )
            refusal = {"message": ROLE_NOT_CONFIRMED} if setup == "refused-login" else None
            httpx2_mock.add_response(url=me, status_code=401, json=refusal, is_reusable=True)
        case "rejected-token":
            monkeypatch.setenv("WHITSON_PVT_TOKEN", "env-token")
            httpx2_mock.add_response(url=me, status_code=401, json={"message": "Invalid token"})
        case "unreachable":
            monkeypatch.setenv("WHITSON_PVT_TOKEN", "env-token")
            httpx2_mock.add_exception(httpx2.ConnectError("refused"), url=me, is_reusable=True)

    result = runner.invoke(app, ["auth", "status", "--json"])

    assert result.exit_code == exit_code
    assert result.stdout == ""
    error = json.loads(result.stderr)
    assert error["error"] == kind
    assert message in error["message"]
    assert absent is None or absent not in error["message"]
    _no_secrets(result)


def test_logout_removes_the_login_and_revokes_its_refresh_token(
    base_url, httpx2_mock, store, store_login
):
    other = "https://other.pvt.whitson.com"
    store_login(other, refresh="other-refresh")
    store_login(base_url, access="stored-access", refresh="stored-refresh")
    httpx2_mock.add_response(
        url=DISCOVERY,
        json={
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}authorize",
            "token_endpoint": TOKEN_ENDPOINT,
            "revocation_endpoint": REVOKE,
        },
    )
    httpx2_mock.add_response(method="POST", url=REVOKE)

    result = runner.invoke(app, ["auth", "logout", "--json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == {
        "removed": [{"url": base_url, "revocation": "revoked", "keyring": "not_used"}]
    }
    assert form(httpx2_mock.get_requests(url=REVOKE)[0]) == {
        "token": "stored-refresh",
        "token_type_hint": "refresh_token",
        "client_id": "cli-client",
    }
    assert store.get(base_url) is None
    assert store.get(other) is not None
    assert store.default_url() is None
    _no_secrets(result)


def test_logout_all_without_revocation_removes_every_login(httpx2_mock, store, store_login):
    urls = ["https://a.pvt.whitson.com", "https://b.pvt.whitson.com"]
    for url in urls:
        store_login(url)
    httpx2_mock.add_response(
        url=DISCOVERY,
        json={
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}authorize",
            "token_endpoint": TOKEN_ENDPOINT,
        },
        is_reusable=True,
    )

    result = runner.invoke(app, ["auth", "logout", "--all", "--json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == {
        "removed": [
            {"url": url, "revocation": "not_offered", "keyring": "not_used"} for url in urls
        ]
    }
    assert all(store.get(url) is None for url in urls)


OTHER_LOGIN_SERVER = {"issuer": "https://login.example.com/"}
OTHER_DEPLOYMENT = {"audience": "https://prod.pvt.whitson.com/mcp"}


@pytest.mark.parametrize(
    ("url", "config", "options", "message"),
    [
        ("https://pvt.example.org", OTHER_LOGIN_SERVER, ["--trust-host"], "--yes"),
        ("http://localhost:4000", OTHER_LOGIN_SERVER, [], "--yes"),
        ("http://localhost:4000", OTHER_DEPLOYMENT, [], "prod.pvt.whitson.com/mcp"),
        ("http://localhost:4000", OTHER_DEPLOYMENT, ["--yes"], "without --yes"),
        (
            "https://pvt.example.org",
            OTHER_DEPLOYMENT,
            ["--trust-host", "--yes"],
            "without --yes",
        ),
    ],
    ids=[
        "trust-host-without-yes",
        "localhost-without-yes",
        "localhost-other-audience-without-yes",
        "localhost-other-audience-yes",
        "trust-host-other-audience-yes",
    ],
)
def test_login_to_another_login_server_asks_or_is_refused(
    httpx2_mock, store, url, config, options, message
):
    httpx2_mock.add_response(
        url=f"{url}/external/v2/auth/config",
        json={**auth_config(), "audience": f"{url}/mcp", **config},
    )

    result = runner.invoke(app, ["auth", "login", "--url", url, "--device", "--json", *options])

    assert result.exit_code == 2
    assert message in result.stderr
    assert "message" in json.loads(result.stderr.splitlines()[-1])
    assert [str(r.url) for r in httpx2_mock.get_requests()] == [f"{url}/external/v2/auth/config"]
    assert store.get(url) is None


def test_trust_host_does_not_apply_to_a_url_from_the_environment(httpx2_mock, monkeypatch):
    monkeypatch.setenv("WHITSON_PVT_URL", "https://pvt.example.org")

    result = runner.invoke(app, ["auth", "login", "--trust-host", "--yes", "--json"])

    assert result.exit_code == 2
    assert "--url" in json.loads(result.stderr.splitlines()[-1])["message"]
    assert httpx2_mock.get_requests() == []


DEVICE_AUTHORIZATION = f"{ISSUER}oauth/device/code"
OFFERED_SCOPES = ["regions:read", "regions:write", "samples:read", "calculations:run"]


def _device_login_server(base_url, httpx2_mock, monkeypatch, scopes=None) -> None:
    monkeypatch.setattr("whitson_pvt_sdk.login.time.sleep", lambda _: None)
    config = auth_config() if scopes is None else {**auth_config(), "scopes": scopes}
    httpx2_mock.add_response(url=f"{base_url}/external/v2/auth/config", json=config)
    httpx2_mock.add_response(
        url=DISCOVERY,
        json={
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}authorize",
            "token_endpoint": TOKEN_ENDPOINT,
            "device_authorization_endpoint": DEVICE_AUTHORIZATION,
        },
    )
    httpx2_mock.add_response(
        method="POST",
        url=DEVICE_AUTHORIZATION,
        json={
            "device_code": "device-secret",
            "user_code": "WXYZ-1234",
            "verification_uri": f"{ISSUER}activate",
            "expires_in": 600,
        },
    )
    httpx2_mock.add_response(
        method="POST",
        url=TOKEN_ENDPOINT,
        json={
            "access_token": "stored-access",
            "refresh_token": "stored-refresh",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
    )


@pytest.mark.parametrize(
    ("env_token", "token_note"), [(None, False), ("", True)], ids=["token-unset", "token-empty"]
)
def test_device_login_makes_the_login_the_default_and_prints_who(
    base_url, httpx2_mock, monkeypatch, store, env_token, token_note
):
    if env_token is not None:
        monkeypatch.setenv("WHITSON_PVT_TOKEN", env_token)
    _device_login_server(base_url, httpx2_mock, monkeypatch)
    httpx2_mock.add_response(url=f"{base_url}/external/v2/me", json=ME)

    result = runner.invoke(app, ["auth", "login", "--url", base_url, "--device", "--json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == {"url": base_url, "identity": IDENTITY, "not_granted": []}
    assert "WXYZ-1234" in result.stderr
    assert [
        r.headers["Authorization"]
        for r in httpx2_mock.get_requests(url=f"{base_url}/external/v2/me")
    ] == ["Bearer stored-access"]
    assert store.default_url() == base_url
    assert ("WHITSON_PVT_TOKEN is set" in result.stderr) is token_note
    _no_secrets(result)


@pytest.mark.parametrize(
    ("me", "exit_code", "message"),
    [
        (
            {"status_code": 403, "json": {"message": "No access to this deployment"}},
            3,
            "No access to this deployment",
        ),
        ({"json": {"kind": "unknown"}}, 4, "kind"),
    ],
    ids=["no-access", "unexpected-identity"],
)
def test_login_whose_identity_check_fails_keeps_the_previous_default(
    base_url, httpx2_mock, monkeypatch, store, store_login, me, exit_code, message
):
    previous = "https://other.pvt.whitson.com"
    store_login(previous)
    _device_login_server(base_url, httpx2_mock, monkeypatch)
    httpx2_mock.add_response(url=f"{base_url}/external/v2/me", **me)

    result = runner.invoke(app, ["auth", "login", "--url", base_url, "--device", "--json"])

    assert result.exit_code == exit_code
    assert result.stdout == ""
    assert message in json.loads(result.stderr.splitlines()[-1])["message"]
    assert store.get(base_url) is None
    assert store.default_url() == previous
    _no_secrets(result)


@pytest.mark.parametrize(
    ("options", "requested"),
    [
        ([], "regions:read regions:write samples:read calculations:run offline_access"),
        (["--scope", "samples:read"], "samples:read offline_access"),
        (
            ["--scope", "calculations:run", "--scope", "read"],
            "regions:read samples:read calculations:run offline_access",
        ),
    ],
    ids=["default-all", "one", "read-shorthand-and-one"],
)
def test_login_requests_the_chosen_scopes_and_offline_access(
    base_url, httpx2_mock, monkeypatch, store, options, requested
):
    _device_login_server(base_url, httpx2_mock, monkeypatch, OFFERED_SCOPES)
    granted = requested.removesuffix(" offline_access").split()
    httpx2_mock.add_response(url=f"{base_url}/external/v2/me", json={**ME, "scopes": granted})

    result = runner.invoke(app, ["auth", "login", "--url", base_url, "--device", *options])

    assert result.exit_code == 0, result.stderr
    assert form(httpx2_mock.get_requests(url=DEVICE_AUTHORIZATION)[0])["scope"] == requested
    assert "Not granted" not in result.stdout
    entry = store.get(base_url)
    assert isinstance(entry, ActiveLogin)
    assert list(entry.login.scopes) == granted


@pytest.mark.parametrize(
    ("offered", "options", "message"),
    [
        (
            OFFERED_SCOPES,
            ["--scope", "samples:read", "--scope", "samples:write"],
            "does not offer the scope samples:write. Choose from regions:read, regions:write, "
            "samples:read, calculations:run, or read for every *:read scope.",
        ),
        (OFFERED_SCOPES, ["--scope", "offline_access"], "does not offer the scope offline_access"),
        (["calculations:run"], ["--scope", "read"], "offers no *:read scope"),
    ],
    ids=["unknown", "offline-access", "read-with-none-offered"],
)
def test_login_refuses_scopes_the_deployment_does_not_offer_before_signing_in(
    base_url, httpx2_mock, store, offered, options, message
):
    config_url = f"{base_url}/external/v2/auth/config"
    httpx2_mock.add_response(url=config_url, json={**auth_config(), "scopes": offered})

    result = runner.invoke(
        app, ["auth", "login", "--url", base_url, "--device", "--json", *options]
    )

    assert result.exit_code == 2
    assert message in json.loads(result.stderr.splitlines()[-1])["message"]
    assert [str(r.url) for r in httpx2_mock.get_requests()] == [config_url]
    assert store.get(base_url) is None


@pytest.mark.parametrize("json_output", [False, True], ids=["text", "json"])
def test_login_reports_scopes_the_role_did_not_grant(
    base_url, httpx2_mock, monkeypatch, json_output
):
    _device_login_server(base_url, httpx2_mock, monkeypatch, OFFERED_SCOPES)
    granted = ["regions:read", "samples:read"]
    httpx2_mock.add_response(url=f"{base_url}/external/v2/me", json={**ME, "scopes": granted})

    scopes = ["--scope", "read", "--scope", "regions:write"]
    output = ["--json"] if json_output else []
    result = runner.invoke(app, ["auth", "login", "--url", base_url, "--device", *scopes, *output])

    assert result.exit_code == 0, result.stderr
    if json_output:
        assert json.loads(result.stdout)["not_granted"] == ["regions:write"]
    else:
        assert "Not granted: regions:write. Your role on" in result.stdout


TERMINAL_TITLE = "\x1b]0;x\x07"


@pytest.mark.parametrize(
    ("argv", "route", "response"),
    [
        (
            ["regions", "list"],
            "regions",
            {
                "json": {
                    "regions": [{"id": 1, "name": f"North {TERMINAL_TITLE}"}],
                    "pagination": {"next_cursor": f"c{TERMINAL_TITLE}", "prev_cursor": None},
                }
            },
        ),
        (["auth", "status"], "me", {"json": {**IDENTITY, "name": f"Ada {TERMINAL_TITLE}"}}),
        (
            ["regions", "list"],
            "regions",
            {"status_code": 400, "json": {"message": f"Bad {TERMINAL_TITLE}"}},
        ),
    ],
    ids=["list-and-cursor", "me", "server-error"],
)
def test_server_text_cannot_send_control_sequences_to_the_terminal(
    base_url, httpx2_mock, monkeypatch, argv, route, response
):
    monkeypatch.setenv("WHITSON_PVT_URL", base_url)
    monkeypatch.setenv("WHITSON_PVT_TOKEN", "env-token")
    httpx2_mock.add_response(url=f"{base_url}/external/v2/{route}", **response)

    result = runner.invoke(app, argv)

    output = result.stdout + result.stderr
    assert "\x1b" not in output and "\x07" not in output
    assert "\\x1b]0;x\\x07" in output


@pytest.mark.parametrize(
    ("missing", "argv", "extra"),
    [("typer", ["wpvt", "--version"], "cli"), ("fastmcp", ["wpvt", "mcp"], "mcp")],
    ids=["cli", "mcp"],
)
def test_wpvt_without_an_extra_prints_the_install_command(missing, argv, extra):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.modules[{missing!r}] = None; "
            f"sys.argv = {argv!r}; "
            "from whitson_pvt_sdk.cli import main; main()",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert f'pip install "whitson-pvt-sdk[{extra}]"' in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.skipif(
    sys.platform in ("win32", "darwin"),
    reason="a shell script stands in for the browser, and macOS would fall back to a real one",
)
@pytest.mark.parametrize(("exit_code", "opened"), [(0, True), (1, False)], ids=["opens", "fails"])
def test_the_browser_writes_nothing_to_the_terminal(
    tmp_path, monkeypatch, capfd, exit_code, opened
):
    browser = tmp_path / "browser"
    visited = tmp_path / "visited"
    browser.write_text(
        f'#!/bin/sh\necho "$1" > {visited}\necho browser log\necho browser error >&2\n'
        f"exit {exit_code}\n"
    )
    browser.chmod(0o755)
    for name in ("DISPLAY", "WAYLAND_DISPLAY", "TERM"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BROWSER", str(browser))
    monkeypatch.setattr(webbrowser, "_tryorder", None)
    monkeypatch.setattr(webbrowser, "_browsers", {})

    result = _open_browser("http://127.0.0.1:52817/start?n=x")
    print("after")  # noqa: T201 - proves the terminal's stdout is restored after the call

    assert result is opened
    assert visited.read_text() == "http://127.0.0.1:52817/start?n=x\n"
    assert capfd.readouterr() == ("after\n", "")

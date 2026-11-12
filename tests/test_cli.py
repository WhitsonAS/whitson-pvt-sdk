import json
import subprocess
import sys
from urllib.parse import parse_qs

import httpx
import pytest
from typer.testing import CliRunner

from tests.conftest import ISSUER, TOKEN_ENDPOINT
from whitson_pvt_sdk.cli._app import app

DISCOVERY = f"{ISSUER}.well-known/openid-configuration"
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
    base_url, httpx_mock, monkeypatch, store_login, use_env_token, credential, identity
):
    store_login(base_url, access="stored-access", refresh="stored-refresh")
    if use_env_token:
        monkeypatch.setenv("WHITSON_PVT_TOKEN", "env-token")
    httpx_mock.add_response(
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


@pytest.fixture
def no_retry_sleep(monkeypatch):
    monkeypatch.setattr("whitson_pvt_sdk.http.time.sleep", lambda _: None)


@pytest.mark.parametrize(
    ("setup", "exit_code", "kind", "message"),
    [
        ("nothing", 2, "configuration", "wpvt auth login --url"),
        ("invalid-login", 3, "authentication", "no longer valid"),
        ("rejected-token", 3, "authentication", "Check the token in WHITSON_PVT_TOKEN"),
        ("unreachable", 4, "network", "Request failed"),
    ],
)
@pytest.mark.usefixtures("no_retry_sleep")
def test_status_failures_have_distinct_exit_codes(
    base_url, httpx_mock, monkeypatch, store, store_login, setup, exit_code, kind, message
):
    monkeypatch.setenv("WHITSON_PVT_URL", base_url)
    me = f"{base_url}/external/v2/me"
    match setup:
        case "invalid-login":
            store_login(base_url, access="stored-access", refresh="stored-refresh")
            with store.transaction() as transaction:
                transaction.mark_invalid(base_url, "the refresh token was revoked")
        case "rejected-token":
            monkeypatch.setenv("WHITSON_PVT_TOKEN", "env-token")
            httpx_mock.add_response(url=me, status_code=401, json={"message": "Invalid token"})
        case "unreachable":
            monkeypatch.setenv("WHITSON_PVT_TOKEN", "env-token")
            httpx_mock.add_exception(httpx.ConnectError("refused"), url=me, is_reusable=True)

    result = runner.invoke(app, ["auth", "status", "--json"])

    assert result.exit_code == exit_code
    assert result.stdout == ""
    error = json.loads(result.stderr)
    assert error["error"] == kind
    assert message in error["message"]
    _no_secrets(result)


def test_logout_removes_the_login_and_revokes_its_refresh_token(
    base_url, httpx_mock, store, store_login
):
    other = "https://other.pvt.whitson.com"
    store_login(other, refresh="other-refresh")
    store_login(base_url, access="stored-access", refresh="stored-refresh")
    httpx_mock.add_response(
        url=DISCOVERY,
        json={
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}authorize",
            "token_endpoint": TOKEN_ENDPOINT,
            "revocation_endpoint": REVOKE,
        },
    )
    httpx_mock.add_response(method="POST", url=REVOKE)

    result = runner.invoke(app, ["auth", "logout", "--json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == {"removed": [{"url": base_url, "revocation": "revoked"}]}
    revocation = parse_qs(httpx_mock.get_requests(url=REVOKE)[0].content.decode())
    assert revocation == {
        "token": ["stored-refresh"],
        "token_type_hint": ["refresh_token"],
        "client_id": ["cli-client"],
    }
    assert store.get(base_url) is None
    assert store.get(other) is not None
    assert store.default_url() is None
    _no_secrets(result)


def test_logout_all_without_revocation_removes_every_login(httpx_mock, store, store_login):
    urls = ["https://a.pvt.whitson.com", "https://b.pvt.whitson.com"]
    for url in urls:
        store_login(url)
    httpx_mock.add_response(
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
        "removed": [{"url": url, "revocation": "not_offered"} for url in urls]
    }
    assert all(store.get(url) is None for url in urls)


AUTH_CONFIG = {
    "issuer": ISSUER,
    "client_id": "cli-client",
    "audience": "https://dev.pvt.whitson.com/mcp",
    "scopes": ["read:data"],
    "device_login": True,
}


OTHER_LOGIN_SERVER = {"issuer": "https://login.example.com/"}
OTHER_DEPLOYMENT = {"audience": "https://prod.pvt.whitson.com/mcp"}


@pytest.mark.parametrize(
    ("url", "config", "options", "exit_code", "message"),
    [
        ("https://pvt.example.org", OTHER_LOGIN_SERVER, ["--trust-host"], 2, "--yes"),
        ("http://localhost:4000", OTHER_LOGIN_SERVER, [], 2, "--yes"),
        ("http://localhost:4000", OTHER_DEPLOYMENT, [], 2, "prod.pvt.whitson.com/mcp"),
        (
            "https://dev.pvt.whitson.com",
            OTHER_LOGIN_SERVER,
            ["--yes"],
            3,
            "unexpected login server",
        ),
        (
            "https://dev.pvt.whitson.com",
            OTHER_LOGIN_SERVER,
            ["--yes", "--trust-host"],
            3,
            "unexpected login server",
        ),
        (
            "https://dev.pvt.whitson.com",
            OTHER_DEPLOYMENT,
            ["--yes", "--trust-host"],
            3,
            "asked for access to a different service, 'https://prod.pvt.whitson.com/mcp'",
        ),
    ],
    ids=[
        "trust-host-without-yes",
        "localhost-without-yes",
        "localhost-other-audience-without-yes",
        "deployment",
        "deployment-trust-host",
        "deployment-other-audience",
    ],
)
def test_login_to_another_login_server_asks_or_is_refused(
    httpx_mock, store, url, config, options, exit_code, message
):
    httpx_mock.add_response(url=f"{url}/external/v2/auth/config", json={**AUTH_CONFIG, **config})

    result = runner.invoke(app, ["auth", "login", "--url", url, "--device", "--json", *options])

    assert result.exit_code == exit_code
    assert message in result.stderr
    assert "message" in json.loads(result.stderr.splitlines()[-1])
    assert [str(r.url) for r in httpx_mock.get_requests()] == [f"{url}/external/v2/auth/config"]
    assert store.get(url) is None


def test_trust_host_does_not_apply_to_a_url_from_the_environment(httpx_mock, monkeypatch):
    monkeypatch.setenv("WHITSON_PVT_URL", "https://pvt.example.org")

    result = runner.invoke(app, ["auth", "login", "--trust-host", "--yes", "--json"])

    assert result.exit_code == 2
    assert "--url" in json.loads(result.stderr.splitlines()[-1])["message"]
    assert httpx_mock.get_requests() == []


def test_device_login_makes_the_login_the_default_and_prints_who(
    base_url, httpx_mock, monkeypatch, store
):
    monkeypatch.setattr("whitson_pvt_sdk.login.time.sleep", lambda _: None)
    httpx_mock.add_response(url=f"{base_url}/external/v2/auth/config", json=AUTH_CONFIG)
    httpx_mock.add_response(
        url=DISCOVERY,
        json={
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}authorize",
            "token_endpoint": TOKEN_ENDPOINT,
            "device_authorization_endpoint": f"{ISSUER}oauth/device/code",
        },
    )
    httpx_mock.add_response(
        method="POST",
        url=f"{ISSUER}oauth/device/code",
        json={
            "device_code": "device-secret",
            "user_code": "WXYZ-1234",
            "verification_uri": f"{ISSUER}activate",
            "expires_in": 600,
        },
    )
    httpx_mock.add_response(
        method="POST",
        url=TOKEN_ENDPOINT,
        json={
            "access_token": "stored-access",
            "refresh_token": "stored-refresh",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
    )
    httpx_mock.add_response(url=f"{base_url}/external/v2/me", json=ME)

    result = runner.invoke(app, ["auth", "login", "--url", base_url, "--device", "--json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == {"url": base_url, "identity": IDENTITY}
    assert "WXYZ-1234" in result.stderr
    assert [
        r.headers["Authorization"]
        for r in httpx_mock.get_requests(url=f"{base_url}/external/v2/me")
    ] == ["Bearer stored-access"]
    assert store.default_url() == base_url
    _no_secrets(result)


def test_wpvt_without_typer_prints_the_install_command():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.modules['typer'] = None; "
            "sys.argv = ['wpvt', '--version']; "
            "from whitson_pvt_sdk.cli import main; main()",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert 'pip install "whitson-pvt-sdk[cli]"' in result.stderr
    assert "Traceback" not in result.stderr

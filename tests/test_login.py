import base64
import hashlib
import re
import threading
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit

import pytest

from tests.conftest import ISSUER, TOKEN_ENDPOINT, make_login
from whitson_pvt_sdk._store import ActiveLogin
from whitson_pvt_sdk.errors import ConfigurationError, LoginError, SDKError
from whitson_pvt_sdk.login import (
    BrowserLogin,
    Confirmation,
    DeviceLogin,
    FirstUse,
    IssuerChanged,
    login,
)

DISCOVERY = f"{ISSUER}.well-known/openid-configuration"
DEVICE_ENDPOINT = "https://login.example.com/oauth/device/code"
AUTHORIZE = "https://login.example.com/authorize"
TOKENS = {
    "access_token": "fresh-access",
    "refresh_token": "fresh-refresh",
    "token_type": "Bearer",
    "expires_in": 3600,
}


@pytest.fixture
def authorization_server(base_url, httpx_mock):
    httpx_mock.add_response(
        url=f"{base_url}/external/v2/auth/config",
        json={
            "issuer": ISSUER,
            "client_id": "cli-client",
            "audience": "https://dev.pvt.whitson.com/external",
            "scopes": ["read:data", "write:data"],
            "connection": "acme-sso",
            "device_login": True,
        },
    )
    httpx_mock.add_response(
        url=DISCOVERY,
        json={
            "issuer": ISSUER,
            "authorization_endpoint": AUTHORIZE,
            "token_endpoint": TOKEN_ENDPOINT,
            "device_authorization_endpoint": DEVICE_ENDPOINT,
        },
    )


def _accept(_: Confirmation) -> bool:
    return True


def _form(request):
    return {key: value[0] for key, value in parse_qs(request.content.decode()).items()}


def _visit_later(urls, statuses) -> threading.Thread:
    def visit():
        for url in urls:
            try:
                with urllib.request.urlopen(url, timeout=5) as response:
                    statuses.append(response.status)
            except urllib.error.HTTPError as error:
                statuses.append(error.code)

    thread = threading.Thread(target=visit)
    thread.start()
    return thread


@pytest.mark.usefixtures("authorization_server")
def test_browser_login_completes_through_the_loopback_callback(base_url, httpx_mock, store):
    httpx_mock.add_response(method="POST", url=TOKEN_ENDPOINT, json=TOKENS)
    opened, messages, statuses, visits = [], [], [], []

    def open_browser(url: str) -> bool:
        opened.append(url)
        query = parse_qs(urlsplit(url).query)
        redirect = query["redirect_uri"][0]
        stray = redirect.replace("/callback", "/favicon.ico")
        visits.append(
            _visit_later([stray, f"{redirect}?code=the-code&state={query['state'][0]}"], statuses)
        )
        return True

    stored = login(
        base_url,
        BrowserLogin(open_browser=open_browser, timeout=10),
        output=messages.append,
        confirm=_accept,
    )
    visits.pop().join()

    authorize = parse_qs(urlsplit(opened[0]).query)
    assert {key: value[0] for key, value in authorize.items() if key not in {"state"}} == {
        "response_type": "code",
        "client_id": "cli-client",
        "redirect_uri": authorize["redirect_uri"][0],
        "scope": "read:data write:data offline_access",
        "audience": "https://dev.pvt.whitson.com/external",
        "code_challenge": authorize["code_challenge"][0],
        "code_challenge_method": "S256",
        "connection": "acme-sso",
    }
    assert authorize["redirect_uri"][0].startswith("http://127.0.0.1:")
    exchange = _form(httpx_mock.get_requests(url=TOKEN_ENDPOINT)[0])
    verifier = exchange.pop("code_verifier")
    digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert digest.decode() == authorize["code_challenge"][0]
    assert exchange == {
        "grant_type": "authorization_code",
        "client_id": "cli-client",
        "code": "the-code",
        "redirect_uri": authorize["redirect_uri"][0],
    }
    assert statuses == [404, 200]
    assert not any(verifier in message or "the-code" in message for message in messages)
    assert stored.access_token.get_secret_value() == "fresh-access"
    assert store.get(base_url) == ActiveLogin(login=stored)
    assert store.default_url() == base_url


@pytest.mark.usefixtures("authorization_server")
def test_browser_callback_with_another_state_is_rejected(base_url, store):
    statuses, visits = [], []

    def open_browser(url: str) -> bool:
        redirect = parse_qs(urlsplit(url).query)["redirect_uri"][0]
        visits.append(_visit_later([f"{redirect}?code=forged-code&state=forged-state"], statuses))
        return True

    with pytest.raises(LoginError, match="state"):
        login(
            base_url,
            BrowserLogin(open_browser=open_browser, timeout=10),
            output=print,
            confirm=_accept,
        )
    visits.pop().join()

    assert statuses == [400]
    assert store.get(base_url) is None


@pytest.mark.parametrize(
    ("url", "deployment"),
    [
        ("https://dev.pvt.whitson.com", "https://dev.pvt.whitson.com"),
        ("https://eu.dev.pvt.whitson.com/", "https://eu.dev.pvt.whitson.com"),
        ("HTTPS://Dev.PVT.Whitson.COM", "https://dev.pvt.whitson.com"),
        ("https://dev.pvt.whitson.com.", "https://dev.pvt.whitson.com"),
        ("http://localhost:4000", "http://localhost:4000"),
        ("https://localhost", "https://localhost"),
        ("http://127.0.0.1:4000", "http://127.0.0.1:4000"),
        ("http://[::1]:4000", "http://[::1]:4000"),
        ("http://mcp.api.pvt.localhost:4000", "http://mcp.api.pvt.localhost:4000"),
    ],
)
def test_login_contacts_a_trusted_deployment(httpx_mock, url, deployment):
    httpx_mock.add_response(status_code=404, json={"message": "Not found"})

    with pytest.raises(
        ConfigurationError, match=re.escape(f"Command-line login is not enabled on {deployment}.")
    ):
        login(url, DeviceLogin(), output=print, confirm=_accept)

    assert [str(r.url) for r in httpx_mock.get_requests()] == [
        f"{deployment}/external/v2/auth/config"
    ]


@pytest.mark.parametrize(
    ("url", "trust_host", "reason"),
    [
        ("https://evilpvt.whitson.com", False, "evilpvt.whitson.com is not a known"),
        ("https://pvt.whitson.com", False, "pvt.whitson.com is not a known"),
        ("https://pvt.whitson.com.evil.example", False, "not a known"),
        ("https://dev.pvt.whitson.com.evil.example", False, "not a known"),
        ("https://dev.pvt-whitson.com", False, "not a known"),
        ("https://localhost.evil.example", False, "not a known"),
        ("http://dev.pvt.whitson.com", True, "plain HTTP"),
        ("http://pvt.example.org", True, "plain HTTP"),
        ("https://ada:secret@dev.pvt.whitson.com", True, "no user name, password"),
        ("https://dev.pvt.whits\u03bfn.com", True, "non-ASCII"),
        ("https://d\u0435v.pvt.whitson.com", True, "non-ASCII"),
        ("https://dev.pvt.xn--whitsn-m0e.com", True, "non-ASCII"),
    ],
)
def test_login_refuses_other_hosts_before_any_request(httpx_mock, url, trust_host, reason):
    with pytest.raises(ConfigurationError, match=reason) as refusal:
        login(url, DeviceLogin(), output=print, confirm=_accept, trust_host=trust_host)

    assert httpx_mock.get_requests() == []
    assert "secret" not in refusal.value.message


def _auth_config(issuer=ISSUER, device_login=True):
    config = {
        "issuer": issuer,
        "client_id": "cli-client",
        "audience": "https://dev.pvt.whitson.com/external",
        "scopes": ["read:data"],
    }
    return config if device_login is None else {**config, "device_login": device_login}


@pytest.mark.parametrize(
    ("stored", "answer", "asked", "error"),
    [
        (
            None,
            False,
            FirstUse(deployment_host="dev.pvt.whitson.com", issuer_host="login.example.com"),
            "cancelled",
        ),
        (None, None, None, "Pass confirm="),
        (
            "other-issuer",
            False,
            IssuerChanged(
                deployment_host="dev.pvt.whitson.com",
                issuer_host="login.example.com",
                previous_issuer_host="old-login.example.com",
            ),
            "cancelled",
        ),
        ("active", None, None, None),
        ("invalid", None, None, None),
    ],
    ids=[
        "first-use-declined",
        "first-use-without-confirm",
        "issuer-changed",
        "known",
        "known-invalid",
    ],
)
def test_login_asks_before_the_first_login_to_a_deployment(
    base_url, httpx_mock, store, stored, answer, asked, error
):
    if stored is not None:
        previous = make_login(base_url, refresh="old-refresh")
        if stored == "other-issuer":
            previous = previous.model_copy(update={"issuer": "https://old-login.example.com/"})
        with store.transaction() as transaction:
            transaction.put(previous)
            if stored == "invalid":
                transaction.mark_invalid(base_url, "the refresh token was revoked")
    httpx_mock.add_response(url=f"{base_url}/external/v2/auth/config", json=_auth_config())
    if error is None:
        httpx_mock.add_response(url=DISCOVERY, status_code=503)
    questions = []

    def confirm(question: Confirmation) -> bool:
        questions.append(question)
        return bool(answer)

    with pytest.raises(SDKError, match=error or "HTTP 503"):
        login(base_url, DeviceLogin(), output=print, confirm=None if answer is None else confirm)

    assert questions == ([] if asked is None else [asked])
    requested = [str(r.url) for r in httpx_mock.get_requests()]
    assert requested == [f"{base_url}/external/v2/auth/config"] + (
        [DISCOVERY] if error is None else []
    )
    entry = store.get(base_url)
    if stored is None:
        assert entry is None
    else:
        assert entry is not None
        assert entry.login.refresh_token.get_secret_value() == "old-refresh"


def test_trust_host_allows_an_unlisted_host_and_still_asks(httpx_mock, store):
    deployment = "https://pvt.example.org"
    httpx_mock.add_response(url=f"{deployment}/external/v2/auth/config", json=_auth_config())
    questions = []

    def decline(question: Confirmation) -> bool:
        questions.append(question)
        return False

    with pytest.raises(LoginError, match="cancelled"):
        login(deployment, DeviceLogin(), output=print, confirm=decline, trust_host=True)

    assert questions == [
        FirstUse(deployment_host="pvt.example.org", issuer_host="login.example.com")
    ]
    assert len(httpx_mock.get_requests()) == 1
    assert store.get(deployment) is None


@pytest.mark.parametrize(
    ("issuer", "provider", "message"),
    [
        ("http://login.example.com/", {}, "issuer"),
        (
            ISSUER,
            {"authorization_endpoint": "http://login.example.com/authorize"},
            "authorization_endpoint",
        ),
        (ISSUER, {"token_endpoint": "http://login.example.com/oauth/token"}, "token_endpoint"),
        (
            ISSUER,
            {"device_authorization_endpoint": "http://login.example.com/oauth/device/code"},
            "device_authorization_endpoint",
        ),
        (
            ISSUER,
            {"revocation_endpoint": "http://login.example.com/oauth/revoke"},
            "revocation_endpoint",
        ),
        (ISSUER, {"authorization_endpoint": "https://phish.example/authorize"}, "phish.example"),
    ],
    ids=["issuer", "authorization", "token", "device", "revocation", "authorization-elsewhere"],
)
def test_login_refuses_insecure_login_servers(
    base_url, httpx_mock, store, issuer, provider, message
):
    httpx_mock.add_response(url=f"{base_url}/external/v2/auth/config", json=_auth_config(issuer))
    if issuer == ISSUER:
        httpx_mock.add_response(
            url=DISCOVERY,
            json={
                "issuer": ISSUER,
                "authorization_endpoint": AUTHORIZE,
                "token_endpoint": TOKEN_ENDPOINT,
                "device_authorization_endpoint": DEVICE_ENDPOINT,
                **provider,
            },
        )
    opened: list[str] = []

    def open_browser(url: str) -> bool:
        opened.append(url)
        return True

    with pytest.raises(LoginError, match=message):
        login(
            base_url,
            BrowserLogin(open_browser=open_browser, timeout=0.1),
            output=print,
            confirm=_accept,
        )

    assert opened == []
    assert store.get(base_url) is None


@pytest.mark.parametrize("device_login", [False, None], ids=["disabled", "absent"])
def test_device_login_needs_the_deployment_to_enable_it(base_url, httpx_mock, device_login):
    httpx_mock.add_response(
        url=f"{base_url}/external/v2/auth/config", json=_auth_config(device_login=device_login)
    )

    with pytest.raises(ConfigurationError, match="Device login is not enabled.*WHITSON_PVT_TOKEN"):
        login(base_url, DeviceLogin(), output=print, confirm=_accept)

    assert len(httpx_mock.get_requests()) == 1


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


PENDING = {"status_code": 400, "json": {"error": "authorization_pending"}}
SLOW_DOWN = {"status_code": 400, "json": {"error": "slow_down"}}
DENIED = {"status_code": 403, "json": {"error": "access_denied"}}
EXPIRED = {"status_code": 400, "json": {"error": "expired_token"}}
GRANTED = {"json": TOKENS}


@pytest.mark.parametrize(
    ("expires_in", "polls", "sleeps", "error"),
    [
        (600, [PENDING, SLOW_DOWN, GRANTED], [5, 5, 10], None),
        (600, [PENDING, DENIED], [5, 5], "denied"),
        (600, [PENDING, EXPIRED], [5, 5], "expired"),
        (12, [PENDING, PENDING, PENDING], [5, 5, 5], "expired"),
    ],
    ids=["pending-slow-down-granted", "denied", "expired", "expired-locally"],
)
@pytest.mark.usefixtures("authorization_server")
def test_device_login_polls_at_the_server_interval(
    base_url, httpx_mock, monkeypatch, store, expires_in, polls, sleeps, error
):
    clock = FakeClock()
    monkeypatch.setattr("whitson_pvt_sdk.login.time.monotonic", clock.monotonic)
    monkeypatch.setattr("whitson_pvt_sdk.login.time.sleep", clock.sleep)
    httpx_mock.add_response(
        method="POST",
        url=DEVICE_ENDPOINT,
        json={
            "device_code": "secret-device-code",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://login.example.com/activate",
            "expires_in": expires_in,
            "interval": 5,
        },
    )
    for poll in polls:
        httpx_mock.add_response(method="POST", url=TOKEN_ENDPOINT, **poll)
    messages = []

    if error is None:
        stored = login(base_url, DeviceLogin(), output=messages.append, confirm=_accept)
        assert stored.refresh_token.get_secret_value() == "fresh-refresh"
        assert store.default_url() == base_url
    else:
        with pytest.raises(LoginError, match=error):
            login(base_url, DeviceLogin(), output=messages.append, confirm=_accept)
        assert store.get(base_url) is None

    assert clock.sleeps == sleeps
    assert "https://login.example.com/activate" in messages[0]
    assert "ABCD-EFGH" in messages[0]
    assert {request.content for request in httpx_mock.get_requests(url=TOKEN_ENDPOINT)} == {
        b"grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code"
        b"&device_code=secret-device-code&client_id=cli-client"
    }

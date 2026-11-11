import base64
import hashlib
import threading
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit

import pytest

from tests.conftest import ISSUER, TOKEN_ENDPOINT
from whitson_pvt_sdk._store import ActiveLogin
from whitson_pvt_sdk.errors import ConfigurationError, LoginError
from whitson_pvt_sdk.login import BrowserLogin, DeviceLogin, login

DISCOVERY = f"{ISSUER}.well-known/openid-configuration"
DEVICE_ENDPOINT = "https://login.example.com/oauth/device/code"
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
        },
    )
    httpx_mock.add_response(
        url=DISCOVERY,
        json={
            "issuer": ISSUER,
            "authorization_endpoint": "https://login.example.com/authorize",
            "token_endpoint": TOKEN_ENDPOINT,
            "device_authorization_endpoint": DEVICE_ENDPOINT,
        },
    )


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
        base_url, BrowserLogin(open_browser=open_browser, timeout=10), output=messages.append
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
        login(base_url, BrowserLogin(open_browser=open_browser, timeout=10), output=print)
    visits.pop().join()

    assert statuses == [400]
    assert store.get(base_url) is None


def test_login_on_a_deployment_without_command_line_login_says_so(base_url, httpx_mock):
    httpx_mock.add_response(
        url=f"{base_url}/external/v2/auth/config",
        status_code=404,
        json={"message": "Command-line login is not enabled"},
    )

    with pytest.raises(
        ConfigurationError, match="Command-line login is not enabled on https://dev.pvt.whitson.com"
    ):
        login(base_url, DeviceLogin(), output=print)


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
        stored = login(base_url, DeviceLogin(), output=messages.append)
        assert stored.refresh_token.get_secret_value() == "fresh-refresh"
        assert store.default_url() == base_url
    else:
        with pytest.raises(LoginError, match=error):
            login(base_url, DeviceLogin(), output=messages.append)
        assert store.get(base_url) is None

    assert clock.sleeps == sleeps
    assert "https://login.example.com/activate" in messages[0]
    assert "ABCD-EFGH" in messages[0]
    assert {request.content for request in httpx_mock.get_requests(url=TOKEN_ENDPOINT)} == {
        b"grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code"
        b"&device_code=secret-device-code&client_id=cli-client"
    }

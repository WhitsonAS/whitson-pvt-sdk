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
DEVICE_ENDPOINT = f"{ISSUER}oauth/device/code"
AUTHORIZE = f"{ISSUER}authorize"
ACTIVATE = f"{ISSUER}activate"
OTHER_ISSUER = "https://login.example.com/"
TOKENS = {
    "access_token": "fresh-access",
    "refresh_token": "fresh-refresh",
    "token_type": "Bearer",
    "expires_in": 3600,
}


@pytest.fixture
def authorization_server(base_url, httpx2_mock):
    httpx2_mock.add_response(
        url=f"{base_url}/external/v2/auth/config",
        json={
            "issuer": ISSUER,
            "client_id": "cli-client",
            "audience": "https://dev.pvt.whitson.com/mcp",
            "scopes": ["read:data", "write:data"],
            "connection": "acme-sso",
            "device_login": True,
        },
    )
    httpx2_mock.add_response(
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
def test_browser_login_completes_through_the_loopback_callback(base_url, httpx2_mock, store):
    httpx2_mock.add_response(method="POST", url=TOKEN_ENDPOINT, json=TOKENS)
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
    )
    visits.pop().join()

    authorize = parse_qs(urlsplit(opened[0]).query)
    assert {key: value[0] for key, value in authorize.items() if key not in {"state"}} == {
        "response_type": "code",
        "client_id": "cli-client",
        "redirect_uri": authorize["redirect_uri"][0],
        "scope": "read:data write:data offline_access",
        "audience": "https://dev.pvt.whitson.com/mcp",
        "code_challenge": authorize["code_challenge"][0],
        "code_challenge_method": "S256",
        "connection": "acme-sso",
    }
    assert authorize["redirect_uri"][0].startswith("http://127.0.0.1:")
    exchange = _form(httpx2_mock.get_requests(url=TOKEN_ENDPOINT)[0])
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
    assert stored.audience == "https://dev.pvt.whitson.com/mcp"
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
def test_login_contacts_a_trusted_deployment(httpx2_mock, url, deployment):
    httpx2_mock.add_response(status_code=404, json={"message": "Not found"})

    with pytest.raises(
        ConfigurationError, match=re.escape(f"Command-line login is not enabled on {deployment}.")
    ):
        login(url, DeviceLogin(), output=print)

    assert [str(r.url) for r in httpx2_mock.get_requests()] == [
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
        ("https://xn--dv-dlc.pvt.whitson.com", False, "non-ASCII"),
        ("https://dev\u3002pvt.whitson.com", False, "non-ASCII"),
    ],
)
def test_login_refuses_other_hosts_before_any_request(httpx2_mock, url, trust_host, reason):
    with pytest.raises(ConfigurationError, match=reason) as refusal:
        login(url, DeviceLogin(), output=print, confirm=_accept, trust_host=trust_host)

    assert httpx2_mock.get_requests() == []
    assert "secret" not in refusal.value.message


def _auth_config(issuer=ISSUER, device_login=True, audience="https://dev.pvt.whitson.com/mcp"):
    config = {
        "issuer": issuer,
        "client_id": "cli-client",
        "audience": audience,
        "scopes": ["read:data"],
    }
    return config if device_login is None else {**config, "device_login": device_login}


LOOPBACK = "http://localhost:4000"
BASE = "https://dev.pvt.whitson.com"
UNLISTED = "https://pvt.example.org"
OLD_ISSUER = "https://old-login.example.com/"
OTHER_DEPLOYMENT = "https://prod.pvt.whitson.com/mcp"
LOCAL_MCP = "http://localhost:8000/mcp"
PROCEEDS = "HTTP 503"
REFUSED = "dev.pvt.whitson.com named an unexpected login server, https://login.example.com"
OTHER_SERVICE = "dev.pvt.whitson.com asked for access to a different service"


def _first_use(deployment_host, issuer_host="login.example.com", foreign_audience=None):
    return FirstUse(
        deployment_host=deployment_host,
        issuer_host=issuer_host,
        foreign_audience=foreign_audience,
    )


def _changed(deployment_host, previous_issuer_host="old-login.example.com"):
    return IssuerChanged(
        deployment_host=deployment_host,
        issuer_host="login.example.com",
        previous_issuer_host=previous_issuer_host,
        foreign_audience=None,
    )


OWN = "own"


@pytest.mark.parametrize(
    ("deployment", "trust_host", "issuer", "audience", "stored", "answer", "asked", "error"),
    [
        pytest.param(BASE, False, ISSUER, OWN, None, None, None, PROCEEDS, id="deployment-known"),
        pytest.param(
            BASE,
            False,
            ISSUER,
            OWN,
            OLD_ISSUER,
            None,
            None,
            PROCEEDS,
            id="deployment-known-changed",
        ),
        pytest.param(
            BASE, False, OTHER_ISSUER, OWN, None, True, None, REFUSED, id="deployment-other"
        ),
        pytest.param(
            BASE,
            True,
            OTHER_ISSUER,
            OWN,
            None,
            True,
            None,
            REFUSED,
            id="deployment-other-trust-host",
        ),
        pytest.param(
            BASE,
            False,
            OTHER_ISSUER,
            OWN,
            OTHER_ISSUER,
            True,
            None,
            REFUSED,
            id="deployment-other-stored",
        ),
        pytest.param(
            BASE,
            True,
            ISSUER,
            OTHER_DEPLOYMENT,
            ISSUER,
            True,
            None,
            OTHER_SERVICE,
            id="deployment-other-audience-stored-trust-host",
        ),
        pytest.param(LOOPBACK, False, ISSUER, OWN, None, None, None, PROCEEDS, id="loopback-known"),
        pytest.param(
            LOOPBACK,
            False,
            ISSUER,
            LOCAL_MCP,
            None,
            False,
            _first_use("localhost", "whitson.eu.auth0.com", LOCAL_MCP),
            "cancelled",
            id="loopback-known-other-audience",
        ),
        pytest.param(
            LOOPBACK,
            False,
            ISSUER,
            LOCAL_MCP,
            ISSUER,
            None,
            None,
            PROCEEDS,
            id="loopback-known-other-audience-known",
        ),
        pytest.param(
            LOOPBACK,
            False,
            OTHER_ISSUER,
            OWN,
            None,
            False,
            _first_use("localhost"),
            "cancelled",
            id="loopback-other-first-use",
        ),
        pytest.param(
            LOOPBACK,
            False,
            OTHER_ISSUER,
            OWN,
            None,
            None,
            None,
            "Pass confirm=",
            id="loopback-other-no-confirm",
        ),
        pytest.param(
            LOOPBACK,
            False,
            OTHER_ISSUER,
            OWN,
            OLD_ISSUER,
            False,
            _changed("localhost"),
            "cancelled",
            id="loopback-other-changed",
        ),
        pytest.param(
            LOOPBACK,
            False,
            OTHER_ISSUER,
            OWN,
            ISSUER,
            False,
            _changed("localhost", "whitson.eu.auth0.com"),
            "cancelled",
            id="loopback-known-to-other",
        ),
        pytest.param(
            LOOPBACK,
            False,
            OTHER_ISSUER,
            OWN,
            OTHER_ISSUER,
            None,
            None,
            PROCEEDS,
            id="loopback-other-known",
        ),
        pytest.param(
            LOOPBACK,
            False,
            OTHER_ISSUER,
            OWN,
            "invalid",
            None,
            None,
            PROCEEDS,
            id="loopback-other-known-invalid",
        ),
        pytest.param(
            UNLISTED,
            True,
            ISSUER,
            OWN,
            None,
            False,
            _first_use("pvt.example.org", "whitson.eu.auth0.com"),
            "cancelled",
            id="trust-host-known",
        ),
        pytest.param(
            UNLISTED,
            True,
            ISSUER,
            OTHER_DEPLOYMENT,
            None,
            False,
            _first_use("pvt.example.org", "whitson.eu.auth0.com", OTHER_DEPLOYMENT),
            "cancelled",
            id="trust-host-known-other-audience",
        ),
        pytest.param(
            UNLISTED,
            True,
            OTHER_ISSUER,
            OWN,
            None,
            False,
            _first_use("pvt.example.org"),
            "cancelled",
            id="trust-host-other",
        ),
        pytest.param(
            UNLISTED,
            True,
            "https://login.xn--exmple-cua.com/",
            OWN,
            None,
            False,
            _first_use("pvt.example.org", "login.xn--exmple-cua.com"),
            "cancelled",
            id="trust-host-punycode-issuer-shown-in-ascii",
        ),
        pytest.param(
            UNLISTED,
            True,
            OTHER_ISSUER,
            OWN,
            OLD_ISSUER,
            False,
            _changed("pvt.example.org"),
            "cancelled",
            id="trust-host-other-changed",
        ),
    ],
)
def test_login_decides_by_deployment_issuer_and_audience(
    httpx2_mock, store, deployment, trust_host, issuer, audience, stored, answer, asked, error
):
    if stored is not None:
        previous = make_login(deployment, refresh="old-refresh")
        previous = previous.model_copy(
            update={"issuer": OTHER_ISSUER if stored == "invalid" else stored}
        )
        with store.transaction() as transaction:
            transaction.put(previous)
            if stored == "invalid":
                transaction.mark_invalid(deployment, "the refresh token was revoked")
    httpx2_mock.add_response(
        url=f"{deployment}/external/v2/auth/config",
        json=_auth_config(issuer, audience=f"{deployment}/mcp" if audience == OWN else audience),
    )
    discovery = f"{issuer}.well-known/openid-configuration"
    if error == PROCEEDS:
        httpx2_mock.add_response(url=discovery, status_code=503)
    questions, opened = [], []

    def confirm(question: Confirmation) -> bool:
        questions.append(question)
        return bool(answer)

    def open_browser(url: str) -> bool:
        opened.append(url)
        return True

    with pytest.raises(SDKError, match=re.escape(error)):
        login(
            deployment,
            BrowserLogin(open_browser=open_browser, timeout=0.1),
            output=print,
            confirm=None if answer is None else confirm,
            trust_host=trust_host,
        )

    assert questions == ([] if asked is None else [asked])
    assert opened == []
    assert [str(r.url) for r in httpx2_mock.get_requests()] == [
        f"{deployment}/external/v2/auth/config"
    ] + ([discovery] if error == PROCEEDS else [])
    entry = store.get(deployment)
    if stored is None:
        assert entry is None
    elif stored != "invalid":
        assert entry is not None
        assert entry.login.refresh_token.get_secret_value() == "old-refresh"


@pytest.mark.parametrize(
    ("issuer", "error"),
    [
        ("https://Whitson.EU.auth0.com/", PROCEEDS),
        ("https://whitson.eu.auth0.com:443/", PROCEEDS),
        ("https://whitson.eu.auth0.com.evil.example/", "unexpected login server"),
        ("https://evil-whitson.eu.auth0.com/", "unexpected login server"),
        ("https://a.whitson.eu.auth0.com/", "unexpected login server"),
        ("https://whitson-login.eu.auth0.com/", "unexpected login server"),
        ("https://whitson.eu.auth0.com:8443/", "unexpected login server"),
        ("http://whitson.eu.auth0.com/", "issuer: Value error, must be an https URL"),
    ],
)
def test_a_deployment_signs_in_only_at_a_known_issuer_host(base_url, httpx2_mock, issuer, error):
    httpx2_mock.add_response(url=f"{base_url}/external/v2/auth/config", json=_auth_config(issuer))
    if error == PROCEEDS:
        httpx2_mock.add_response(status_code=503)

    with pytest.raises(SDKError, match=re.escape(error)):
        login(base_url, DeviceLogin(), output=print, confirm=_accept, trust_host=True)

    requests = [r.url for r in httpx2_mock.get_requests()]
    assert [str(url) for url in requests[:1]] == [f"{base_url}/external/v2/auth/config"]
    assert [url.host for url in requests[1:]] == (
        ["whitson.eu.auth0.com"] if error == PROCEEDS else []
    )


@pytest.mark.parametrize("trust_host", [False, True], ids=["allowlisted", "trust-host"])
@pytest.mark.parametrize(
    ("audience", "error"),
    [
        ("https://dev.pvt.whitson.com/mcp", PROCEEDS),
        ("https://Dev.PVT.Whitson.com/mcp", PROCEEDS),
        ("https://dev.pvt.whitson.com:443/mcp", PROCEEDS),
        ("https://prod.pvt.whitson.com/mcp", OTHER_SERVICE),
        ("https://dev.pvt.whitson.com/external", OTHER_SERVICE),
        ("https://dev.pvt.whitson.com/mcp/", OTHER_SERVICE),
        ("https://dev.pvt.whitson.com/mcp/x", OTHER_SERVICE),
        ("https://dev.pvt.whitson.com/MCP", OTHER_SERVICE),
        ("https://dev.pvt.whitson.com/mcp?resource=prod", OTHER_SERVICE),
        ("https://dev.pvt.whitson.com", OTHER_SERVICE),
        ("https://dev.pvt.whitson.com:8443/mcp", OTHER_SERVICE),
        ("http://dev.pvt.whitson.com/mcp", OTHER_SERVICE),
        ("https://dev.pvt.whitson.com.evil.example/mcp", OTHER_SERVICE),
        ("https://eu.dev.pvt.whitson.com/mcp", OTHER_SERVICE),
        ("urn:whitson:prod", OTHER_SERVICE),
    ],
)
def test_a_deployment_may_only_ask_for_access_to_itself(
    base_url, httpx2_mock, store, audience, error, trust_host
):
    httpx2_mock.add_response(
        url=f"{base_url}/external/v2/auth/config", json=_auth_config(audience=audience)
    )
    if error == PROCEEDS:
        httpx2_mock.add_response(url=DISCOVERY, status_code=503)
    opened: list[str] = []

    def open_browser(url: str) -> bool:
        opened.append(url)
        return True

    with pytest.raises(SDKError, match=re.escape(error)):
        login(
            base_url,
            BrowserLogin(open_browser=open_browser, timeout=0.1),
            output=print,
            confirm=_accept,
            trust_host=trust_host,
        )

    assert [str(r.url) for r in httpx2_mock.get_requests()] == [
        f"{base_url}/external/v2/auth/config"
    ] + ([DISCOVERY] if error == PROCEEDS else [])
    assert opened == []
    assert store.get(base_url) is None


@pytest.mark.parametrize(
    ("issuer", "provider", "message"),
    [
        ("http://whitson.eu.auth0.com/", {}, "issuer"),
        (
            ISSUER,
            {"authorization_endpoint": "http://whitson.eu.auth0.com/authorize"},
            "authorization_endpoint",
        ),
        (ISSUER, {"token_endpoint": "http://whitson.eu.auth0.com/oauth/token"}, "token_endpoint"),
        (
            ISSUER,
            {"device_authorization_endpoint": "http://whitson.eu.auth0.com/oauth/device/code"},
            "device_authorization_endpoint",
        ),
        (
            ISSUER,
            {"revocation_endpoint": "http://whitson.eu.auth0.com/oauth/revoke"},
            "revocation_endpoint",
        ),
        (ISSUER, {"authorization_endpoint": "https://phish.example/authorize"}, "phish.example"),
    ],
    ids=["issuer", "authorization", "token", "device", "revocation", "authorization-elsewhere"],
)
def test_login_refuses_insecure_login_servers(
    base_url, httpx2_mock, store, issuer, provider, message
):
    httpx2_mock.add_response(url=f"{base_url}/external/v2/auth/config", json=_auth_config(issuer))
    if issuer == ISSUER:
        httpx2_mock.add_response(
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
        )

    assert opened == []
    assert store.get(base_url) is None


DEVICE_DISABLED = "Device login is not enabled"


@pytest.mark.parametrize(
    ("deployment", "config", "error"),
    [
        pytest.param(BASE, _auth_config(device_login=False), DEVICE_DISABLED, id="disabled"),
        pytest.param(BASE, _auth_config(device_login=None), DEVICE_DISABLED, id="absent"),
        pytest.param(
            BASE,
            _auth_config(OTHER_ISSUER, device_login=False),
            REFUSED,
            id="unexpected-issuer-first",
        ),
        pytest.param(
            BASE,
            _auth_config(device_login=False, audience=OTHER_DEPLOYMENT),
            OTHER_SERVICE,
            id="unexpected-audience-first",
        ),
        pytest.param(
            LOOPBACK,
            _auth_config(OTHER_ISSUER, device_login=False),
            DEVICE_DISABLED,
            id="before-the-question",
        ),
    ],
)
def test_device_login_needs_the_deployment_to_enable_it(httpx2_mock, deployment, config, error):
    httpx2_mock.add_response(url=f"{deployment}/external/v2/auth/config", json=config)
    questions: list[Confirmation] = []

    def confirm(question: Confirmation) -> bool:
        questions.append(question)
        return True

    with pytest.raises(SDKError, match=re.escape(error)):
        login(deployment, DeviceLogin(), output=print, confirm=confirm)

    assert questions == []
    assert len(httpx2_mock.get_requests()) == 1


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
    base_url, httpx2_mock, monkeypatch, store, expires_in, polls, sleeps, error
):
    clock = FakeClock()
    monkeypatch.setattr("whitson_pvt_sdk.login.time.monotonic", clock.monotonic)
    monkeypatch.setattr("whitson_pvt_sdk.login.time.sleep", clock.sleep)
    httpx2_mock.add_response(
        method="POST",
        url=DEVICE_ENDPOINT,
        json={
            "device_code": "secret-device-code",
            "user_code": "ABCD-EFGH",
            "verification_uri": ACTIVATE,
            "expires_in": expires_in,
            "interval": 5,
        },
    )
    for poll in polls:
        httpx2_mock.add_response(method="POST", url=TOKEN_ENDPOINT, **poll)
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
    assert ACTIVATE in messages[0]
    assert "ABCD-EFGH" in messages[0]
    assert {request.content for request in httpx2_mock.get_requests(url=TOKEN_ENDPOINT)} == {
        b"grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code"
        b"&device_code=secret-device-code&client_id=cli-client"
    }


@pytest.mark.parametrize(
    ("pages", "message"),
    [
        ({"verification_uri": "https://phish.example/activate"}, "phish.example"),
        ({"verification_uri": "http://whitson.eu.auth0.com/activate"}, "cannot use"),
        (
            {"verification_uri_complete": "https://phish.example/activate?user_code=ABCD"},
            "phish.example",
        ),
        ({"verification_uri_complete": "http://whitson.eu.auth0.com/activate"}, "cannot use"),
    ],
    ids=["elsewhere", "http", "complete-elsewhere", "complete-http"],
)
@pytest.mark.usefixtures("authorization_server")
def test_device_login_refuses_a_code_page_off_the_login_server(
    base_url, httpx2_mock, store, pages, message
):
    httpx2_mock.add_response(
        method="POST",
        url=DEVICE_ENDPOINT,
        json={
            "device_code": "secret-device-code",
            "user_code": "ABCD-EFGH",
            "verification_uri": ACTIVATE,
            "expires_in": 600,
            **pages,
        },
    )
    messages = []

    with pytest.raises(LoginError, match=message):
        login(base_url, DeviceLogin(), output=messages.append)

    assert messages == []
    assert httpx2_mock.get_requests(url=TOKEN_ENDPOINT) == []
    assert store.get(base_url) is None

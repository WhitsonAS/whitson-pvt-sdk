import base64
import hashlib
import re
import socket
import threading
import urllib.error
import urllib.request
from email.message import Message
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import BaseModel, ConfigDict

from tests.conftest import DISCOVERY, ISSUER, TOKEN_ENDPOINT, auth_config, form, make_login
from whitson_pvt_sdk._store import ActiveLogin
from whitson_pvt_sdk.credentials import StoredLogin
from whitson_pvt_sdk.errors import APIError, ConfigurationError, LoginError, SDKError
from whitson_pvt_sdk.login import (
    CALLBACK_PORTS,
    AudienceChanged,
    BrowserLogin,
    Confirmation,
    DeviceLogin,
    FirstUse,
    IssuerChanged,
    login,
)

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

STARTED = (302, None)
LOGGED_IN = (200, "Logged in")
NOT_FOUND = (404, "Not found")


PROVIDER = {
    "issuer": ISSUER,
    "authorization_endpoint": AUTHORIZE,
    "token_endpoint": TOKEN_ENDPOINT,
    "device_authorization_endpoint": DEVICE_ENDPOINT,
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
    httpx2_mock.add_response(url=DISCOVERY, json=PROVIDER)


def _accept(_: Confirmation) -> bool:
    return True


def _keep(stored: StoredLogin) -> StoredLogin:
    return stored


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


_BROWSER = urllib.request.build_opener(_NoRedirects)


class _Response(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: int
    location: str | None
    headers: dict[str, str]
    body: str

    @property
    def outcome(self) -> tuple[int, str | None]:
        heading = re.search(r"<h1>(.*?)</h1>", self.body)
        return self.status, None if heading is None else heading[1]


def _get(url: str) -> _Response:
    try:
        with _BROWSER.open(url, timeout=5) as response:
            return _response(response.status, response.headers, response.read())
    except urllib.error.HTTPError as error:
        with error:
            return _response(error.code, error.headers, error.read())


def _response(status: int, headers: Message, body: bytes) -> _Response:
    return _Response(
        status=status,
        location=headers.get("Location"),
        headers=dict(headers),
        body=body.decode(),
    )


def _query(url: str) -> dict[str, str]:
    return {key: value[0] for key, value in parse_qs(urlsplit(url).query).items()}


def _browser_later(start_url: str, responses, then) -> threading.Thread:
    def browse():
        if urlsplit(start_url).hostname != "127.0.0.1":
            return
        start = _get(start_url)
        responses.append(start)
        for url in then(start.location or ""):
            responses.append(_get(url))

    thread = threading.Thread(target=browse)
    thread.start()
    return thread


@pytest.mark.usefixtures("authorization_server")
def test_browser_login_completes_through_the_loopback_callback(base_url, httpx2_mock, store):
    httpx2_mock.add_response(method="POST", url=TOKEN_ENDPOINT, json=TOKENS)
    authorized, messages, responses, visits = [], [], [], []

    def sign_in(authorize: str) -> list[str]:
        authorized.append(authorize)
        query = _query(authorize)
        redirect = query["redirect_uri"]
        stray = redirect.replace("/callback", "/favicon.ico")
        return [stray, f"{redirect}?code=the-code&state={query['state']}"]

    def open_browser(url: str) -> bool:
        visits.append(_browser_later(url, responses, sign_in))
        return True

    stored = login(
        base_url,
        BrowserLogin(open_browser=open_browser, timeout=10),
        output=messages.append,
        verify=_keep,
    )
    visits.pop().join()

    authorize = _query(authorized[0])
    assert authorized[0].startswith(f"{AUTHORIZE}?")
    assert {key: value for key, value in authorize.items() if key != "state"} == {
        "response_type": "code",
        "client_id": "cli-client",
        "redirect_uri": authorize["redirect_uri"],
        "scope": "read:data write:data offline_access",
        "audience": "https://dev.pvt.whitson.com/mcp",
        "code_challenge": authorize["code_challenge"],
        "code_challenge_method": "S256",
        "connection": "acme-sso",
    }
    redirect = urlsplit(authorize["redirect_uri"])
    assert (redirect.hostname, redirect.port, redirect.path) == (
        "127.0.0.1",
        CALLBACK_PORTS[0],
        "/callback",
    )
    exchange = form(httpx2_mock.get_requests(url=TOKEN_ENDPOINT)[0])
    verifier = exchange.pop("code_verifier")
    digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert digest.decode() == authorize["code_challenge"]
    assert exchange == {
        "grant_type": "authorization_code",
        "client_id": "cli-client",
        "code": "the-code",
        "redirect_uri": authorize["redirect_uri"],
    }
    assert [response.outcome for response in responses] == [STARTED, NOT_FOUND, LOGGED_IN]
    for page in responses[1:]:
        assert (page.headers["Content-Security-Policy"], page.headers["Cache-Control"]) == (
            "default-src 'none'; style-src 'unsafe-inline'",
            "no-store",
        )
        assert page.headers["Content-Type"] == "text/html; charset=utf-8"
        assert not re.search(r"https?://", page.body)
    assert not any(verifier in message or "the-code" in message for message in messages)
    assert stored.access_token.get_secret_value() == "fresh-access"
    assert stored.audience == "https://dev.pvt.whitson.com/mcp"
    assert store.get(base_url) == ActiveLogin(login=stored)
    assert store.default_url() == base_url


@pytest.mark.parametrize("then_valid", [True, False], ids=["then-valid", "only-forged"])
@pytest.mark.usefixtures("authorization_server")
def test_browser_callback_with_another_state_is_rejected(base_url, httpx2_mock, store, then_valid):
    if then_valid:
        httpx2_mock.add_response(method="POST", url=TOKEN_ENDPOINT, json=TOKENS)
    responses, visits = [], []

    def sign_in(authorize: str) -> list[str]:
        query = _query(authorize)
        redirect = query["redirect_uri"]
        forged = [f"{redirect}?code=forged-code&state=forged-state", f"{redirect}?code=forged-code"]
        valid = [f"{redirect}?code=the-code&state={query['state']}"] if then_valid else []
        return forged + valid

    def open_browser(url: str) -> bool:
        visits.append(_browser_later(url, responses, sign_in))
        return True

    def attempt():
        return login(
            base_url, BrowserLogin(open_browser=open_browser, timeout=2), output=print, verify=_keep
        )

    if then_valid:
        stored = attempt()
        assert store.get(base_url) == ActiveLogin(login=stored)
    else:
        with pytest.raises(LoginError, match="Timed out"):
            attempt()
        assert store.get(base_url) is None
    visits.pop().join()

    other_login = (400, "Unexpected login")
    assert [response.outcome for response in responses] == [
        STARTED,
        other_login,
        other_login,
    ] + ([LOGGED_IN] if then_valid else [])
    assert [form(request)["code"] for request in httpx2_mock.get_requests(url=TOKEN_ENDPOINT)] == (
        ["the-code"] if then_valid else []
    )


@pytest.mark.parametrize(
    ("suffixes", "outcomes", "failure"),
    [
        ([""], [STARTED, LOGGED_IN], None),
        (["x", ""], [NOT_FOUND, STARTED, LOGGED_IN], None),
        (["%C3%A9", ""], [NOT_FOUND, STARTED, LOGGED_IN], None),
        (["", ""], [STARTED, (400, "Link already used")], "opened more than once"),
    ],
    ids=["once", "wrong-nonce-ignored", "non-ascii-nonce-ignored", "twice"],
)
@pytest.mark.usefixtures("authorization_server")
def test_the_browser_gets_a_one_time_start_link_instead_of_the_login_page(
    base_url, httpx2_mock, store, suffixes, outcomes, failure
):
    if failure is None:
        httpx2_mock.add_response(method="POST", url=TOKEN_ENDPOINT, json=TOKENS)
    opened, messages, seen, authorized, visits = [], [], [], [], []

    def browse(start_url: str) -> None:
        for suffix in suffixes:
            response = _get(f"{start_url}{suffix}")
            seen.append(response.outcome)
            if response.location is not None:
                authorized.append(response.location)
        if failure is None:
            query = _query(authorized[0])
            callback = f"{query['redirect_uri']}?code=the-code&state={query['state']}"
            seen.append(_get(callback).outcome)

    def open_browser(url: str) -> bool:
        opened.append(url)
        if urlsplit(url).hostname == "127.0.0.1":
            visits.append(threading.Thread(target=browse, args=(url,)))
            visits[-1].start()
        return True

    try:
        outcome: StoredLogin | LoginError = login(
            base_url,
            BrowserLogin(open_browser=open_browser, timeout=5),
            output=messages.append,
            verify=_keep,
        )
    except LoginError as refusal:
        outcome = refusal
    for visit in visits:
        visit.join()

    start = urlsplit(opened[0])
    assert (start.scheme, start.hostname, start.path, set(_query(opened[0]))) == (
        "http",
        "127.0.0.1",
        "/start",
        {"n"},
    )
    assert not any("state=" in message or "code_challenge" in message for message in messages)
    assert opened[0] in messages[0]
    assert seen == outcomes
    assert len(authorized) == 1
    assert authorized[0].startswith(f"{AUTHORIZE}?")
    assert [form(request)["code"] for request in httpx2_mock.get_requests(url=TOKEN_ENDPOINT)] == (
        ["the-code"] if failure is None else []
    )
    if failure is None:
        assert isinstance(outcome, StoredLogin)
        assert store.get(base_url) == ActiveLogin(login=outcome)
    else:
        assert isinstance(outcome, LoginError)
        assert failure in outcome.message
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
    ],
)
def test_login_contacts_a_trusted_deployment(httpx2_mock, url, deployment):
    httpx2_mock.add_response(status_code=404, json={"message": "Not found"})

    with pytest.raises(
        ConfigurationError, match=re.escape(f"Command-line login is not enabled on {deployment}.")
    ):
        login(url, DeviceLogin(), output=print, verify=_keep)

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
        login(
            url, DeviceLogin(), output=print, verify=_keep, confirm=_accept, trust_host=trust_host
        )

    assert httpx2_mock.get_requests() == []
    assert "secret" not in refusal.value.message


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


def _audience_changed(
    deployment_host, previous_audience, foreign_audience, issuer_host="whitson.eu.auth0.com"
):
    return AudienceChanged(
        deployment_host=deployment_host,
        issuer_host=issuer_host,
        previous_audience=previous_audience,
        foreign_audience=foreign_audience,
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
            (OLD_ISSUER, OWN),
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
            (OTHER_ISSUER, OWN),
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
            (ISSUER, OTHER_DEPLOYMENT),
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
            (ISSUER, LOCAL_MCP),
            None,
            None,
            PROCEEDS,
            id="loopback-known-other-audience-known",
        ),
        pytest.param(
            LOOPBACK,
            False,
            ISSUER,
            LOCAL_MCP,
            (ISSUER, OWN),
            False,
            _audience_changed("localhost", "http://localhost:4000/mcp", LOCAL_MCP),
            "cancelled",
            id="loopback-known-issuer-other-audience",
        ),
        pytest.param(
            LOOPBACK,
            False,
            OTHER_ISSUER,
            LOCAL_MCP,
            (OTHER_ISSUER, OTHER_DEPLOYMENT),
            False,
            _audience_changed("localhost", OTHER_DEPLOYMENT, LOCAL_MCP, "login.example.com"),
            "cancelled",
            id="loopback-other-issuer-another-foreign-audience",
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
            (OLD_ISSUER, OWN),
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
            (ISSUER, OWN),
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
            (OTHER_ISSUER, OWN),
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
            ISSUER,
            OTHER_DEPLOYMENT,
            (ISSUER, OWN),
            False,
            _audience_changed(
                "pvt.example.org",
                "https://pvt.example.org/mcp",
                OTHER_DEPLOYMENT,
                "whitson.eu.auth0.com",
            ),
            "cancelled",
            id="trust-host-known-issuer-other-audience",
        ),
        pytest.param(
            UNLISTED,
            True,
            ISSUER,
            OWN,
            (ISSUER, OTHER_DEPLOYMENT),
            False,
            _audience_changed("pvt.example.org", OTHER_DEPLOYMENT, None, "whitson.eu.auth0.com"),
            "cancelled",
            id="trust-host-foreign-audience-to-own",
        ),
        pytest.param(
            UNLISTED,
            True,
            ISSUER,
            OTHER_DEPLOYMENT,
            (ISSUER, OTHER_DEPLOYMENT),
            None,
            None,
            PROCEEDS,
            id="trust-host-known-issuer-and-audience",
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
            (OLD_ISSUER, OWN),
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
        stored_issuer, stored_audience = (OTHER_ISSUER, OWN) if stored == "invalid" else stored
        previous = make_login(deployment, refresh="old-refresh").model_copy(
            update={
                "issuer": stored_issuer,
                "audience": f"{deployment}/mcp" if stored_audience == OWN else stored_audience,
            }
        )
        with store.transaction() as transaction:
            transaction.put(previous)
            if stored == "invalid":
                transaction.mark_invalid(deployment, "the refresh token was revoked")
    httpx2_mock.add_response(
        url=f"{deployment}/external/v2/auth/config",
        json=auth_config(issuer, audience=f"{deployment}/mcp" if audience == OWN else audience),
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
            verify=_keep,
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
    httpx2_mock.add_response(url=f"{base_url}/external/v2/auth/config", json=auth_config(issuer))
    if error == PROCEEDS:
        httpx2_mock.add_response(status_code=503)

    with pytest.raises(SDKError, match=re.escape(error)):
        login(base_url, DeviceLogin(), output=print, verify=_keep, confirm=_accept, trust_host=True)

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
        url=f"{base_url}/external/v2/auth/config", json=auth_config(audience=audience)
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
            verify=_keep,
            confirm=_accept,
            trust_host=trust_host,
        )

    assert [str(r.url) for r in httpx2_mock.get_requests()] == [
        f"{base_url}/external/v2/auth/config"
    ] + ([DISCOVERY] if error == PROCEEDS else [])
    assert opened == []
    assert store.get(base_url) is None


@pytest.mark.parametrize(
    ("provider", "message"),
    [
        (
            {"authorization_endpoint": "http://whitson.eu.auth0.com/authorize"},
            "authorization_endpoint",
        ),
        ({"token_endpoint": "http://whitson.eu.auth0.com/oauth/token"}, "token_endpoint"),
        (
            {"device_authorization_endpoint": "http://whitson.eu.auth0.com/oauth/device/code"},
            "device_authorization_endpoint",
        ),
        (
            {"revocation_endpoint": "http://whitson.eu.auth0.com/oauth/revoke"},
            "revocation_endpoint",
        ),
        ({"authorization_endpoint": "https://phish.example/authorize"}, "phish.example"),
    ],
    ids=["authorization", "token", "device", "revocation", "authorization-elsewhere"],
)
def test_login_refuses_insecure_login_servers(base_url, httpx2_mock, store, provider, message):
    httpx2_mock.add_response(url=f"{base_url}/external/v2/auth/config", json=auth_config())
    httpx2_mock.add_response(url=DISCOVERY, json={**PROVIDER, **provider})
    opened: list[str] = []

    def open_browser(url: str) -> bool:
        opened.append(url)
        return True

    with pytest.raises(LoginError, match=message):
        login(
            base_url,
            BrowserLogin(open_browser=open_browser, timeout=0.1),
            output=print,
            verify=_keep,
        )

    assert opened == []
    assert store.get(base_url) is None


DEVICE_DISABLED = "Device login is not enabled"


@pytest.mark.parametrize(
    ("deployment", "config", "error"),
    [
        pytest.param(BASE, auth_config(device_login=False), DEVICE_DISABLED, id="disabled"),
        pytest.param(BASE, auth_config(device_login=None), DEVICE_DISABLED, id="absent"),
        pytest.param(
            BASE,
            auth_config(OTHER_ISSUER, device_login=False),
            REFUSED,
            id="unexpected-issuer-first",
        ),
        pytest.param(
            BASE,
            auth_config(device_login=False, audience=OTHER_DEPLOYMENT),
            OTHER_SERVICE,
            id="unexpected-audience-first",
        ),
        pytest.param(
            LOOPBACK,
            auth_config(OTHER_ISSUER, device_login=False),
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
        login(deployment, DeviceLogin(), output=print, verify=_keep, confirm=confirm)

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


PENDING = {"status_code": 403, "json": {"error": "authorization_pending"}}
SLOW_DOWN = {"status_code": 429, "json": {"error": "slow_down"}}
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
        stored = login(base_url, DeviceLogin(), output=messages.append, verify=_keep)
        assert stored.refresh_token.get_secret_value() == "fresh-refresh"
        assert store.default_url() == base_url
    else:
        with pytest.raises(LoginError, match=error):
            login(base_url, DeviceLogin(), output=messages.append, verify=_keep)
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
        login(base_url, DeviceLogin(), output=messages.append, verify=_keep)

    assert messages == []
    assert httpx2_mock.get_requests(url=TOKEN_ENDPOINT) == []
    assert store.get(base_url) is None


@pytest.mark.parametrize("busy", [1, len(CALLBACK_PORTS)], ids=["first-busy", "all-busy"])
@pytest.mark.usefixtures("authorization_server")
def test_browser_login_listens_on_the_first_free_registered_port(base_url, busy):
    occupied = []
    for port in CALLBACK_PORTS[:busy]:
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        listener.listen()
        occupied.append(listener)
    ports = []

    def open_browser(url: str) -> bool:
        ports.append(urlsplit(url).port)
        return True

    try:
        with pytest.raises(LoginError) as failure:
            login(
                base_url,
                BrowserLogin(open_browser=open_browser, timeout=0.1),
                output=print,
                verify=_keep,
            )
    finally:
        for listener in occupied:
            listener.close()

    if busy == len(CALLBACK_PORTS):
        assert ports == []
        assert all(str(port) in failure.value.message for port in CALLBACK_PORTS)
    else:
        assert ports == [CALLBACK_PORTS[1]]
        assert "Timed out" in failure.value.message


LOCAL_NAME = "mcp.api.pvt.localhost"


@pytest.mark.parametrize(
    ("addresses", "error"),
    [
        (["127.0.0.1", "::1"], "Command-line login is not enabled"),
        (["127.0.0.1", "10.0.0.5"], "10.0.0.5"),
        (["192.0.2.7"], "192.0.2.7"),
        ([], "does not resolve"),
    ],
    ids=["loopback", "loopback-and-other", "other", "unresolved"],
)
def test_a_name_under_localhost_must_resolve_only_to_this_machine(
    httpx2_mock, monkeypatch, addresses, error
):
    resolve = socket.getaddrinfo

    def getaddrinfo(host, *args, **kwargs):
        if host != LOCAL_NAME:
            return resolve(host, *args, **kwargs)
        if not addresses:
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
        return [
            (socket.AF_INET6 if ":" in a else socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 0))
            for a in addresses
        ]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    accepted = addresses == ["127.0.0.1", "::1"]
    if accepted:
        httpx2_mock.add_response(status_code=404, json={"message": "Not found"})

    with pytest.raises(ConfigurationError, match=re.escape(error)):
        login(f"http://{LOCAL_NAME}:4000", DeviceLogin(), output=print, verify=_keep)

    assert [str(r.url) for r in httpx2_mock.get_requests()] == (
        [f"http://{LOCAL_NAME}:4000/external/v2/auth/config"] if accepted else []
    )


DEVICE_AUTHORIZATION = {
    "device_code": "secret-device-code",
    "user_code": "ABCD-EFGH",
    "verification_uri": ACTIVATE,
    "expires_in": 600,
}


@pytest.mark.parametrize("malformed", ["auth-config", "device-authorization", "token"])
def test_a_malformed_login_server_response_is_a_server_error(
    base_url, httpx2_mock, monkeypatch, store, malformed
):
    monkeypatch.setattr("whitson_pvt_sdk.login.time.sleep", lambda _: None)
    config = auth_config()
    httpx2_mock.add_response(
        url=f"{base_url}/external/v2/auth/config",
        json={**config, "client_id": None} if malformed == "auth-config" else config,
    )
    if malformed != "auth-config":
        httpx2_mock.add_response(url=DISCOVERY, json=PROVIDER)
        httpx2_mock.add_response(
            method="POST",
            url=DEVICE_ENDPOINT,
            json={"user_code": "ABCD-EFGH"}
            if malformed == "device-authorization"
            else DEVICE_AUTHORIZATION,
        )
    if malformed == "token":
        httpx2_mock.add_response(method="POST", url=TOKEN_ENDPOINT, json={"access_token": "x"})

    with pytest.raises(APIError, match="cannot use"):
        login(base_url, DeviceLogin(), output=print, verify=_keep)

    assert store.get(base_url) is None

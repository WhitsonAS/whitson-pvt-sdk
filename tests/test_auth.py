from datetime import timedelta
from urllib.parse import parse_qs

import httpx
import pytest

from tests.conftest import TOKEN_ENDPOINT
from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk._store import ActiveLogin, InvalidLogin
from whitson_pvt_sdk.errors import AuthError, ConfigurationError, LoginError
from whitson_pvt_sdk.http import HTTPTransport

EMPTY_PAGE = {"regions": [], "pagination": {"next_cursor": None, "prev_cursor": None}}
RENEWED = {
    "access_token": "new-access",
    "refresh_token": "new-refresh",
    "token_type": "Bearer",
    "expires_in": 3600,
}
SOON = timedelta(minutes=2)


def _bearers(httpx_mock, url):
    return [r.headers["Authorization"] for r in httpx_mock.get_requests() if str(r.url) == url]


def _token_requests(httpx_mock):
    return [
        parse_qs(r.content.decode())
        for r in httpx_mock.get_requests()
        if str(r.url) == TOKEN_ENDPOINT
    ]


def _active(store, base_url):
    entry = store.get(base_url)
    assert isinstance(entry, ActiveLogin)
    return entry.login


def test_expiring_login_is_renewed_before_the_request(base_url, httpx_mock, store, store_login):
    store_login(base_url, access="old-access", refresh="old-refresh", expires_in=SOON)
    httpx_mock.add_response(method="POST", url=TOKEN_ENDPOINT, json=RENEWED)
    regions = f"{base_url}/external/v2/regions"
    httpx_mock.add_response(url=regions, json=EMPTY_PAGE)

    WhitsonPVTClient(base_url=base_url).regions.list()

    assert _token_requests(httpx_mock) == [
        {
            "grant_type": ["refresh_token"],
            "client_id": ["cli-client"],
            "refresh_token": ["old-refresh"],
        }
    ]
    assert _bearers(httpx_mock, regions) == ["Bearer new-access"]
    stored = _active(store, base_url)
    assert stored.refresh_token.get_secret_value() == "new-refresh"
    assert stored.access_token.get_secret_value() == "new-access"
    assert stored.audience == "https://dev.pvt.whitson.com/mcp"


def test_rejected_login_is_renewed_once_and_the_request_retried(
    base_url, httpx_mock, store, store_login
):
    store_login(base_url, access="old-access", refresh="old-refresh")
    regions = f"{base_url}/external/v2/regions"
    sent = []

    def api(request: httpx.Request) -> httpx.Response:
        sent.append(request.headers["Authorization"])
        if len(sent) == 1:
            return httpx.Response(
                401,
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
                json={"message": "Token expired"},
            )
        return httpx.Response(200, json=EMPTY_PAGE)

    httpx_mock.add_callback(api, url=regions, is_reusable=True)
    httpx_mock.add_response(method="POST", url=TOKEN_ENDPOINT, json=RENEWED)

    WhitsonPVTClient(base_url=base_url).regions.list()

    assert sent == ["Bearer old-access", "Bearer new-access"]
    assert len(_token_requests(httpx_mock)) == 1
    assert _active(store, base_url).refresh_token.get_secret_value() == "new-refresh"


def test_second_rejection_raises_auth_error(base_url, httpx_mock, store_login):
    store_login(base_url)
    regions = f"{base_url}/external/v2/regions"
    for _ in range(2):
        httpx_mock.add_response(url=regions, status_code=401, json={"message": "User disabled"})
    httpx_mock.add_response(method="POST", url=TOKEN_ENDPOINT, json=RENEWED)

    with pytest.raises(AuthError, match="User disabled"):
        WhitsonPVTClient(base_url=base_url).regions.list()

    assert len(_bearers(httpx_mock, regions)) == 2
    assert len(_token_requests(httpx_mock)) == 1


def test_refused_renewal_marks_the_login_and_says_to_log_in(
    base_url, httpx_mock, store, store_login
):
    store_login(base_url, refresh="old-refresh", expires_in=SOON)
    httpx_mock.add_response(
        method="POST",
        url=TOKEN_ENDPOINT,
        status_code=403,
        json={"error": "invalid_grant", "error_description": "Unknown or invalid refresh token."},
    )

    with pytest.raises(
        LoginError, match="wpvt auth login --url https://dev.pvt.whitson.com"
    ) as exc:
        WhitsonPVTClient(base_url=base_url).regions.list()

    assert "old-refresh" not in str(exc.value)
    assert [str(r.url) for r in httpx_mock.get_requests()] == [TOKEN_ENDPOINT]
    entry = store.get(base_url)
    assert isinstance(entry, InvalidLogin)
    assert "invalid_grant" in entry.reason
    with pytest.raises(LoginError, match="no longer valid.*invalid_grant"):
        WhitsonPVTClient(base_url=base_url)


def test_login_renewed_by_another_process_is_used_without_a_token_request(
    base_url, httpx_mock, store_login
):
    store_login(base_url, access="old-access", refresh="old-refresh", expires_in=SOON)
    client = WhitsonPVTClient(base_url=base_url)
    store_login(base_url, access="renewed-elsewhere", refresh="rotated-elsewhere")
    regions = f"{base_url}/external/v2/regions"
    httpx_mock.add_response(url=regions, json=EMPTY_PAGE)

    client.regions.list()

    assert _token_requests(httpx_mock) == []
    assert _bearers(httpx_mock, regions) == ["Bearer renewed-elsewhere"]


@pytest.mark.parametrize(
    "other_url",
    [
        "https://tenant-b.pvt.whitson.com",
        "http://tenant-a.pvt.whitson.com",
        "https://tenant-a.pvt.whitson.com:8443",
    ],
    ids=["host", "scheme", "port"],
)
def test_stored_login_is_never_sent_to_another_deployment(httpx_mock, store_login, other_url):
    login = store_login("https://tenant-a.pvt.whitson.com")
    transport = HTTPTransport(login, other_url)

    with pytest.raises(ConfigurationError, match="Refusing to send the stored login"):
        transport.get("/regions")

    assert httpx_mock.get_requests() == []

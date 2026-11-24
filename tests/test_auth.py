import re
from datetime import timedelta

import httpx2
import pytest

from tests.conftest import EMPTY_PAGE, TOKEN_ENDPOINT, active_login, form
from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk._store import InvalidLogin
from whitson_pvt_sdk.errors import AuthError, ConfigurationError, LoginError
from whitson_pvt_sdk.http import HTTPTransport

RENEWED = {
    "access_token": "new-access",
    "refresh_token": "new-refresh",
    "token_type": "Bearer",
    "expires_in": 3600,
}
SOON = timedelta(minutes=2)


def _bearers(httpx2_mock, url):
    return [r.headers["Authorization"] for r in httpx2_mock.get_requests(url=url)]


def _token_requests(httpx2_mock):
    return [form(r) for r in httpx2_mock.get_requests(url=TOKEN_ENDPOINT)]


def test_expiring_login_is_renewed_before_the_request(base_url, httpx2_mock, store, store_login):
    store_login(base_url, access="old-access", refresh="old-refresh", expires_in=SOON)
    httpx2_mock.add_response(method="POST", url=TOKEN_ENDPOINT, json=RENEWED)
    regions = f"{base_url}/external/v2/regions"
    httpx2_mock.add_response(url=regions, json=EMPTY_PAGE)

    WhitsonPVTClient(base_url=base_url).regions.list()

    assert _token_requests(httpx2_mock) == [
        {
            "grant_type": "refresh_token",
            "client_id": "cli-client",
            "refresh_token": "old-refresh",
        }
    ]
    assert _bearers(httpx2_mock, regions) == ["Bearer new-access"]
    stored = active_login(store, base_url)
    assert stored.refresh_token.get_secret_value() == "new-refresh"
    assert stored.access_token.get_secret_value() == "new-access"
    assert stored.audience == "https://dev.pvt.whitson.com/mcp"


def test_rejected_login_is_renewed_once_and_the_request_retried(
    base_url, httpx2_mock, store, store_login
):
    store_login(base_url, access="old-access", refresh="old-refresh")
    regions = f"{base_url}/external/v2/regions"
    sent = []

    def api(request: httpx2.Request) -> httpx2.Response:
        sent.append(request.headers["Authorization"])
        if len(sent) == 1:
            return httpx2.Response(
                401,
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
                json={"message": "Token expired"},
            )
        return httpx2.Response(200, json=EMPTY_PAGE)

    httpx2_mock.add_callback(api, url=regions, is_reusable=True)
    httpx2_mock.add_response(method="POST", url=TOKEN_ENDPOINT, json=RENEWED)

    WhitsonPVTClient(base_url=base_url).regions.list()

    assert sent == ["Bearer old-access", "Bearer new-access"]
    assert len(_token_requests(httpx2_mock)) == 1
    assert active_login(store, base_url).refresh_token.get_secret_value() == "new-refresh"


def test_second_rejection_raises_auth_error(base_url, httpx2_mock, store_login):
    store_login(base_url)
    regions = f"{base_url}/external/v2/regions"
    for _ in range(2):
        httpx2_mock.add_response(url=regions, status_code=401, json={"message": "User disabled"})
    httpx2_mock.add_response(method="POST", url=TOKEN_ENDPOINT, json=RENEWED)

    with pytest.raises(AuthError, match="User disabled"):
        WhitsonPVTClient(base_url=base_url).regions.list()

    assert len(_bearers(httpx2_mock, regions)) == 2
    assert len(_token_requests(httpx2_mock)) == 1


def test_refused_renewal_marks_the_login_and_says_to_log_in(
    base_url, httpx2_mock, store, store_login
):
    store_login(base_url, refresh="old-refresh", expires_in=SOON)
    httpx2_mock.add_response(
        method="POST",
        url=TOKEN_ENDPOINT,
        status_code=403,
        json={"error": "invalid_grant", "error_description": "Unknown or invalid refresh token."},
    )

    with pytest.raises(
        LoginError, match=re.escape("wpvt auth login --url https://dev.pvt.whitson.com")
    ) as exc:
        WhitsonPVTClient(base_url=base_url).regions.list()

    assert "old-refresh" not in str(exc.value)
    assert [str(r.url) for r in httpx2_mock.get_requests()] == [TOKEN_ENDPOINT]
    entry = store.get(base_url)
    assert isinstance(entry, InvalidLogin)
    assert "invalid_grant" in entry.reason
    with pytest.raises(LoginError, match=r"no longer valid.*invalid_grant"):
        WhitsonPVTClient(base_url=base_url)


def test_login_renewed_by_another_process_is_used_without_a_token_request(
    base_url, httpx2_mock, store_login
):
    store_login(base_url, access="old-access", refresh="old-refresh", expires_in=SOON)
    client = WhitsonPVTClient(base_url=base_url)
    store_login(base_url, access="renewed-elsewhere", refresh="rotated-elsewhere")
    regions = f"{base_url}/external/v2/regions"
    httpx2_mock.add_response(url=regions, json=EMPTY_PAGE)

    client.regions.list()

    assert _token_requests(httpx2_mock) == []
    assert _bearers(httpx2_mock, regions) == ["Bearer renewed-elsewhere"]


@pytest.mark.parametrize("replaced_by", ["active", "invalid"])
def test_login_replaced_by_another_client_is_neither_renewed_nor_used(
    base_url, httpx2_mock, store, store_login, replaced_by
):
    store_login(base_url, access="old-access", refresh="old-refresh")
    client = WhitsonPVTClient(base_url=base_url)
    store_login(base_url, access="other-access", refresh="other-refresh", client_id="other-client")
    if replaced_by == "invalid":
        with store.transaction() as transaction:
            transaction.mark_invalid(base_url, "the authorization server refused to renew it")
    before = store.get(base_url)
    regions = f"{base_url}/external/v2/regions"
    httpx2_mock.add_response(url=regions, status_code=401, json={"message": "Token revoked"})

    with pytest.raises(LoginError, match="a login with another issuer or client replaced it"):
        client.regions.list()

    assert _bearers(httpx2_mock, regions) == ["Bearer old-access"]
    assert _token_requests(httpx2_mock) == []
    assert store.get(base_url) == before


@pytest.mark.parametrize(
    "other_url",
    [
        "https://tenant-b.pvt.whitson.com",
        "http://tenant-a.pvt.whitson.com",
        "https://tenant-a.pvt.whitson.com:8443",
    ],
    ids=["host", "scheme", "port"],
)
def test_stored_login_is_never_sent_to_another_deployment(httpx2_mock, store_login, other_url):
    login = store_login("https://tenant-a.pvt.whitson.com")
    transport = HTTPTransport(login, other_url)

    with pytest.raises(ConfigurationError, match="Refusing to send the stored login"):
        transport.get("/regions")

    assert httpx2_mock.get_requests() == []

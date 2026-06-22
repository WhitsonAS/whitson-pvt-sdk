import json

import httpx
import pytest

from whitson_pvt_sdk.auth import TokenManager
from whitson_pvt_sdk.errors import AuthError
from whitson_pvt_sdk.http import HTTPTransport
from whitson_pvt_sdk.shared.models import ClientCredentials

TOKEN_URL = "https://dev.pvt.whitson.com/external/v2/auth/token"


def test_exchanges_token_on_first_call(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=TOKEN_URL,
        json={"access_token": "tok-1", "expires_in": 86400, "token_type": "Bearer"},
    )
    tm = TokenManager(
        ClientCredentials(client_id="id", client_secret="secret"),
        token_url=TOKEN_URL,
    )
    token = tm.get_token()
    assert token == "tok-1"

    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    body = json.loads(requests[0].read().decode())
    assert body == {"client_id": "id", "client_secret": "secret"}


def test_reuses_cached_token(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=TOKEN_URL,
        json={"access_token": "tok-1", "expires_in": 86400, "token_type": "Bearer"},
    )
    tm = TokenManager(
        ClientCredentials(client_id="id", client_secret="secret"),
        token_url=TOKEN_URL,
    )
    t1 = tm.get_token()
    t2 = tm.get_token()
    t3 = tm.get_token()
    assert t1 == t2 == t3 == "tok-1"
    assert len(httpx_mock.get_requests()) == 1


def test_re_exchanges_when_token_near_expiry(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=TOKEN_URL,
        json={"access_token": "tok-1", "expires_in": 1, "token_type": "Bearer"},
    )
    httpx_mock.add_response(
        method="POST",
        url=TOKEN_URL,
        json={"access_token": "tok-2", "expires_in": 86400, "token_type": "Bearer"},
    )
    tm = TokenManager(
        ClientCredentials(client_id="id", client_secret="secret"),
        token_url=TOKEN_URL,
    )
    t1 = tm.get_token()
    assert t1 == "tok-1"
    t2 = tm.get_token()
    assert t2 == "tok-2"
    assert len(httpx_mock.get_requests()) == 2


def test_raises_auth_error_on_timeout(httpx_mock):
    httpx_mock.add_exception(
        httpx.TimeoutException("timed out"),
        url=TOKEN_URL,
    )
    tm = TokenManager(
        ClientCredentials(client_id="id", client_secret="secret"),
        token_url=TOKEN_URL,
    )
    with pytest.raises(AuthError, match="Authentication service timeout"):
        tm.get_token()


def test_raises_auth_error_on_http_error(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=TOKEN_URL,
        status_code=500,
    )
    tm = TokenManager(
        ClientCredentials(client_id="id", client_secret="secret"),
        token_url=TOKEN_URL,
    )
    with pytest.raises(AuthError, match="Authentication service unavailable"):
        tm.get_token()


def test_raises_auth_error_with_detail_on_status_error(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=TOKEN_URL,
        status_code=401,
        json={
            "error": "access_denied",
            "error_description": "Invalid client credentials",
        },
    )
    tm = TokenManager(
        ClientCredentials(client_id="bad", client_secret="bad"),
        token_url=TOKEN_URL,
    )
    with pytest.raises(AuthError, match="Authentication failed: Invalid client credentials"):
        tm.get_token()


def test_uses_api_token_endpoint(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=TOKEN_URL,
        json={"access_token": "tok-1", "expires_in": 86400, "token_type": "Bearer"},
    )
    tm = TokenManager(
        ClientCredentials(client_id="id", client_secret="secret"),
        token_url=TOKEN_URL,
    )
    assert tm.get_token() == "tok-1"

    body = json.loads(httpx_mock.get_requests()[0].read().decode())
    assert body == {"client_id": "id", "client_secret": "secret"}


def test_transport_exposes_access_token(credentials, base_url, httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=TOKEN_URL,
        json={"access_token": "tok-1", "expires_in": 86400, "token_type": "Bearer"},
    )
    transport = HTTPTransport(credentials, base_url, version="v2")

    assert transport.get_access_token() == "tok-1"
    assert len(httpx_mock.get_requests()) == 1

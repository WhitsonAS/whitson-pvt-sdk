import json
import threading
import time

import httpx
import pytest

from whitson_pvt_sdk.auth import TokenManager
from whitson_pvt_sdk.errors import AuthError
from whitson_pvt_sdk.http import HTTPTransport
from whitson_pvt_sdk.shared.models import ClientCredentials, RetryConfig

TOKEN_URL = "https://dev.pvt.whitson.com/external/v2/auth/token"
_NO_RETRY = RetryConfig(max_attempts=1)


@pytest.fixture
def no_token_sleep(monkeypatch):
    monkeypatch.setattr("whitson_pvt_sdk.auth.time.sleep", lambda _: None)


def _token_response() -> dict:
    return {"access_token": "tok-1", "expires_in": 86400, "token_type": "Bearer"}


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


def test_get_token_is_thread_safe(monkeypatch):
    exchange_count = 0
    count_lock = threading.Lock()
    thread_count = 8
    ready = threading.Barrier(thread_count)

    def fake_post(url, json, timeout):  # noqa: A002 - matches httpx.post signature
        nonlocal exchange_count
        with count_lock:
            exchange_count += 1
        time.sleep(0.02)
        request = httpx.Request("POST", url)
        return httpx.Response(200, json=_token_response(), request=request)

    monkeypatch.setattr("whitson_pvt_sdk.auth.httpx.post", fake_post)
    tm = TokenManager(
        ClientCredentials(client_id="id", client_secret="secret"),
        token_url=TOKEN_URL,
    )
    results: list[str] = []
    results_lock = threading.Lock()

    def worker() -> None:
        ready.wait()
        token = tm.get_token()
        with results_lock:
            results.append(token)

    threads = [threading.Thread(target=worker) for _ in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert exchange_count == 1
    assert results == ["tok-1"] * thread_count


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
        retry_config=_NO_RETRY,
    )
    with pytest.raises(AuthError, match="Authentication service timeout"):
        tm.get_token()


def test_raises_auth_error_on_http_error(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=TOKEN_URL,
        status_code=500,
        headers={"x-request-id": "req-token"},
        text="server failed",
    )
    tm = TokenManager(
        ClientCredentials(client_id="id", client_secret="secret"),
        token_url=TOKEN_URL,
        retry_config=_NO_RETRY,
    )
    with pytest.raises(AuthError, match="Authentication service unavailable") as exc:
        tm.get_token()
    assert exc.value.status_code == 500
    assert exc.value.request_id == "req-token"
    assert exc.value.response_body == "server failed"


def test_token_exchange_retries_429_then_succeeds(httpx_mock, monkeypatch):
    sleeps = []
    monkeypatch.setattr("whitson_pvt_sdk.auth.time.sleep", sleeps.append)
    httpx_mock.add_response(
        method="POST",
        url=TOKEN_URL,
        status_code=429,
        headers={"retry-after": "0"},
        text="too many",
    )
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
    assert len(httpx_mock.get_requests()) == 2
    assert sleeps == [0]


@pytest.mark.usefixtures("no_token_sleep")
def test_retries_token_exchange_on_transient_5xx(httpx_mock):
    httpx_mock.add_response(method="POST", url=TOKEN_URL, status_code=503, text="unavailable")
    httpx_mock.add_response(method="POST", url=TOKEN_URL, json=_token_response())
    tm = TokenManager(
        ClientCredentials(client_id="id", client_secret="secret"),
        token_url=TOKEN_URL,
    )

    assert tm.get_token() == "tok-1"
    assert len(httpx_mock.get_requests()) == 2


def test_token_exchange_honors_retry_after_on_429(httpx_mock, monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("whitson_pvt_sdk.auth.time.sleep", sleeps.append)
    httpx_mock.add_response(
        method="POST",
        url=TOKEN_URL,
        status_code=429,
        headers={"retry-after": "2"},
        text="slow down",
    )
    httpx_mock.add_response(method="POST", url=TOKEN_URL, json=_token_response())
    tm = TokenManager(
        ClientCredentials(client_id="id", client_secret="secret"),
        token_url=TOKEN_URL,
    )

    assert tm.get_token() == "tok-1"
    assert sleeps == [2]


@pytest.mark.usefixtures("no_token_sleep")
def test_token_exchange_gives_up_after_max_attempts(httpx_mock):
    for _ in range(3):
        httpx_mock.add_response(method="POST", url=TOKEN_URL, status_code=502, text="bad gateway")
    tm = TokenManager(
        ClientCredentials(client_id="id", client_secret="secret"),
        token_url=TOKEN_URL,
        retry_config=RetryConfig(max_attempts=3),
    )

    with pytest.raises(AuthError, match="Authentication service unavailable"):
        tm.get_token()
    assert len(httpx_mock.get_requests()) == 3


@pytest.mark.usefixtures("no_token_sleep")
def test_token_exchange_retries_timeout_then_succeeds(httpx_mock):
    httpx_mock.add_exception(httpx.TimeoutException("timed out"), url=TOKEN_URL)
    httpx_mock.add_response(method="POST", url=TOKEN_URL, json=_token_response())
    tm = TokenManager(
        ClientCredentials(client_id="id", client_secret="secret"),
        token_url=TOKEN_URL,
    )

    assert tm.get_token() == "tok-1"
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.usefixtures("no_token_sleep")
def test_token_exchange_does_not_retry_non_transient_4xx(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=TOKEN_URL,
        status_code=401,
        json={"error_description": "Invalid client credentials"},
    )
    tm = TokenManager(
        ClientCredentials(client_id="bad", client_secret="bad"),
        token_url=TOKEN_URL,
    )

    with pytest.raises(AuthError, match="Invalid client credentials"):
        tm.get_token()
    assert len(httpx_mock.get_requests()) == 1


def test_raises_auth_error_with_detail_on_status_error(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=TOKEN_URL,
        status_code=401,
        headers={"x-request-id": "req-bad-auth"},
        json={
            "error": "access_denied",
            "error_description": "Invalid client credentials",
        },
    )
    tm = TokenManager(
        ClientCredentials(client_id="bad", client_secret="bad"),
        token_url=TOKEN_URL,
    )
    with pytest.raises(AuthError, match="Authentication failed: Invalid client credentials") as exc:
        tm.get_token()
    assert exc.value.status_code == 401
    assert exc.value.request_id == "req-bad-auth"
    assert exc.value.response_body == {
        "error": "access_denied",
        "error_description": "Invalid client credentials",
    }


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

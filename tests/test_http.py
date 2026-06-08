import httpx
import pytest

from whitson_pvt_sdk.errors import APIError, AuthError, NotFoundError, ValidationError
from whitson_pvt_sdk.http import HTTPTransport
from whitson_pvt_sdk.shared.models import ClientCredentials, RetryConfig


def _requests_to(httpx_mock, url: str):
    return [request for request in httpx_mock.get_requests() if str(request.url) == url]


@pytest.fixture
def no_retry_sleep(monkeypatch):
    monkeypatch.setattr("whitson_pvt_sdk.http.time.sleep", lambda _: None)


@pytest.fixture
def recorded_sleeps(monkeypatch):
    sleeps = []
    monkeypatch.setattr("whitson_pvt_sdk.http.time.sleep", sleeps.append)
    return sleeps


@pytest.mark.usefixtures("auth_mock")
def test_strips_trailing_slash_from_base_url(httpx_mock):
    httpx_mock.add_response(url="https://pvt.whitson.com/external/v2/test", json={})
    t = HTTPTransport(
        ClientCredentials(client_id="id", client_secret="secret"),
        "https://pvt.whitson.com/",
        version="v2",
    )
    t.get("/test")
    req = httpx_mock.get_requests()[-1]
    assert str(req.url) == "https://pvt.whitson.com/external/v2/test"


@pytest.mark.usefixtures("auth_mock")
def test_includes_version_in_base_url(httpx_mock):
    httpx_mock.add_response(url="https://pvt.whitson.com/external/v1/test", json={})
    t = HTTPTransport(
        ClientCredentials(client_id="id", client_secret="secret"),
        "https://pvt.whitson.com",
        version="v1",
    )
    t.get("/test")
    req = httpx_mock.get_requests()[-1]
    assert str(req.url) == "https://pvt.whitson.com/external/v1/test"


def test_get_returns_parsed_json(transport, httpx_mock):
    httpx_mock.add_response(url="https://pvt.whitson.com/external/v2/regions", json={"regions": []})
    result = transport.get("/regions")
    assert result == {"regions": []}


def test_get_passes_query_params(transport, httpx_mock):
    httpx_mock.add_response(url="https://pvt.whitson.com/external/v2/regions?cursor=abc", json={})
    transport.get("/regions", params={"cursor": "abc"})
    req = httpx_mock.get_requests()[-1]
    assert req.url.query == b"cursor=abc"


def test_post_sends_json_body(transport, httpx_mock):
    httpx_mock.add_response(
        method="POST", url="https://pvt.whitson.com/external/v2/regions", json={"id": 1}
    )
    result = transport.post("/regions", body={"name": "test"})
    assert result == {"id": 1}
    body = httpx_mock.get_requests()[-1].read().decode()
    assert '"name"' in body


def test_put_sends_json_body(transport, httpx_mock):
    httpx_mock.add_response(
        method="PUT", url="https://pvt.whitson.com/external/v2/regions/1", json={"id": 1}
    )
    result = transport.put("/regions/1", body={"name": "updated"})
    assert result == {"id": 1}


def test_get_bytes_returns_raw_bytes(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/reports/1/export",
        content=b"binary-data",
    )
    result = transport.get_bytes("/reports/1/export")
    assert result == b"binary-data"


def test_post_multipart_sends_files_and_data(transport, httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://pvt.whitson.com/external/v2/reports/import",
        json={"ok": True},
    )
    result = transport.post_multipart(
        "/reports/import",
        files={"file": ("archive.zip", b"data", "application/zip")},
        data={"meta_data": '{"region_id": 1}'},
    )
    assert result == {"ok": True}


def test_401_raises_auth_error(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/test",
        status_code=401,
        json={"message": "Unauthorized"},
    )
    with pytest.raises(AuthError, match="Unauthorized"):
        transport.get("/test")


def test_403_raises_auth_error(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/test",
        status_code=403,
        json={"message": "Forbidden"},
    )
    with pytest.raises(AuthError, match="Forbidden"):
        transport.get("/test")


def test_404_raises_not_found_error(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/test",
        status_code=404,
        json={"message": "Not found"},
    )
    with pytest.raises(NotFoundError, match="Not found"):
        transport.get("/test")


def test_400_raises_validation_error(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/test",
        status_code=400,
        json={"message": "Bad request"},
    )
    with pytest.raises(ValidationError, match="Bad request"):
        transport.get("/test")


def test_422_raises_validation_error(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/test",
        status_code=422,
        json={"message": "Validation failed"},
    )
    with pytest.raises(ValidationError, match="Validation failed"):
        transport.get("/test")


@pytest.mark.usefixtures("no_retry_sleep")
def test_500_raises_api_error_with_status_code(transport, httpx_mock):
    for _ in range(3):
        httpx_mock.add_response(
            url="https://pvt.whitson.com/external/v2/test",
            status_code=500,
            json={"message": "Internal error"},
        )
    with pytest.raises(APIError, match="Internal error") as exc:
        transport.get("/test")
    assert exc.value.status_code == 500


@pytest.mark.usefixtures("no_retry_sleep")
def test_get_retries_500_then_succeeds(transport, httpx_mock):
    url = "https://pvt.whitson.com/external/v2/test"
    httpx_mock.add_response(url=url, status_code=500, json={"message": "Try again"})
    httpx_mock.add_response(url=url, json={"ok": True})

    assert transport.get("/test") == {"ok": True}
    assert len(_requests_to(httpx_mock, url)) == 2


def test_get_retries_429_then_succeeds(transport, httpx_mock, recorded_sleeps):
    url = "https://pvt.whitson.com/external/v2/test"
    httpx_mock.add_response(
        url=url,
        status_code=429,
        headers={"retry-after": "0"},
        json={"message": "Too many requests"},
    )
    httpx_mock.add_response(url=url, json={"ok": True})

    assert transport.get("/test") == {"ok": True}
    assert len(_requests_to(httpx_mock, url)) == 2
    assert recorded_sleeps == [0]


def test_retry_uses_retry_after_ms(transport, httpx_mock, recorded_sleeps):
    url = "https://pvt.whitson.com/external/v2/test"
    httpx_mock.add_response(
        url=url,
        status_code=429,
        headers={"retry-after-ms": "1500"},
        json={"message": "Too many requests"},
    )
    httpx_mock.add_response(url=url, json={"ok": True})

    assert transport.get("/test") == {"ok": True}
    assert recorded_sleeps == [1.5]


def test_retry_uses_http_date_retry_after(transport, httpx_mock, monkeypatch, recorded_sleeps):
    monkeypatch.setattr("whitson_pvt_sdk.http.time.time", lambda: 1_700_000_000)
    url = "https://pvt.whitson.com/external/v2/test"
    httpx_mock.add_response(
        url=url,
        status_code=429,
        headers={"retry-after": "Tue, 14 Nov 2023 22:13:25 GMT"},
        json={"message": "Too many requests"},
    )
    httpx_mock.add_response(url=url, json={"ok": True})

    assert transport.get("/test") == {"ok": True}
    assert recorded_sleeps == [5]


def test_retry_uses_rate_limit_reset(transport, httpx_mock, monkeypatch, recorded_sleeps):
    monkeypatch.setattr("whitson_pvt_sdk.http.time.time", lambda: 1_700_000_000)
    url = "https://pvt.whitson.com/external/v2/test"
    httpx_mock.add_response(
        url=url,
        status_code=429,
        headers={"x-ratelimit-reset": "1700000007"},
        json={"message": "Too many requests"},
    )
    httpx_mock.add_response(url=url, json={"ok": True})

    assert transport.get("/test") == {"ok": True}
    assert recorded_sleeps == [7]


@pytest.mark.usefixtures("no_retry_sleep")
def test_get_retries_timeout_then_succeeds(transport, httpx_mock):
    url = "https://pvt.whitson.com/external/v2/test"
    httpx_mock.add_exception(httpx.TimeoutException("Timed out"), url=url)
    httpx_mock.add_response(url=url, json={"ok": True})

    assert transport.get("/test") == {"ok": True}
    assert len(_requests_to(httpx_mock, url)) == 2


@pytest.mark.usefixtures("no_retry_sleep")
def test_get_final_retryable_status_raises_api_error(transport, httpx_mock):
    url = "https://pvt.whitson.com/external/v2/test"
    for _ in range(3):
        httpx_mock.add_response(url=url, status_code=503, json={"message": "Unavailable"})

    with pytest.raises(APIError, match="Unavailable") as exc:
        transport.get("/test")

    assert exc.value.status_code == 503
    assert len(_requests_to(httpx_mock, url)) == 3


@pytest.mark.usefixtures("no_retry_sleep")
def test_post_does_not_retry_500_by_default(transport, httpx_mock):
    url = "https://pvt.whitson.com/external/v2/test"
    httpx_mock.add_response(
        method="POST", url=url, status_code=500, json={"message": "Internal error"}
    )

    with pytest.raises(APIError, match="Internal error") as exc:
        transport.post("/test", body={"name": "test"})

    assert exc.value.status_code == 500
    assert len(_requests_to(httpx_mock, url)) == 1


@pytest.mark.usefixtures("no_retry_sleep")
def test_get_bytes_retries_502_then_succeeds(transport, httpx_mock):
    url = "https://pvt.whitson.com/external/v2/reports/1/export"
    httpx_mock.add_response(url=url, status_code=502, text="Bad gateway")
    httpx_mock.add_response(url=url, content=b"binary-data")

    assert transport.get_bytes("/reports/1/export") == b"binary-data"
    assert len(_requests_to(httpx_mock, url)) == 2


@pytest.mark.usefixtures("no_retry_sleep")
@pytest.mark.usefixtures("auth_mock")
def test_retry_config_max_attempts_one_disables_retries(
    credentials, base_url, httpx_mock
):
    transport = HTTPTransport(
        credentials,
        base_url,
        version="v2",
        retry_config=RetryConfig(max_attempts=1),
    )
    url = "https://pvt.whitson.com/external/v2/test"
    httpx_mock.add_response(url=url, status_code=503, json={"message": "Unavailable"})

    with pytest.raises(APIError, match="Unavailable"):
        transport.get("/test")

    assert len(_requests_to(httpx_mock, url)) == 1


def test_timeout_configures_default_http_timeout(credentials, base_url):
    transport = HTTPTransport(credentials, base_url, version="v2", timeout=12.5)

    assert transport._http.timeout.read == 12.5


@pytest.mark.usefixtures("auth_mock")
def test_file_timeout_configures_download_timeout(credentials, base_url, httpx_mock):
    transport = HTTPTransport(credentials, base_url, version="v2", file_timeout=19.5)
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/reports/1/export",
        content=b"binary-data",
    )

    assert transport.get_bytes("/reports/1/export") == b"binary-data"
    assert httpx_mock.get_requests()[-1].extensions["timeout"]["read"] == 19.5


def test_uses_response_text_when_no_message_field(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/test",
        status_code=400,
        text="plain text error",
    )
    with pytest.raises(ValidationError, match="plain text error"):
        transport.get("/test")


@pytest.mark.usefixtures("no_retry_sleep")
def test_falls_back_to_http_code_when_body_empty(transport, httpx_mock):
    for _ in range(3):
        httpx_mock.add_response(
            url="https://pvt.whitson.com/external/v2/test",
            status_code=502,
            content=b"",
        )
    with pytest.raises(APIError, match="HTTP 502") as exc:
        transport.get("/test")
    assert exc.value.status_code == 502


def test_context_manager_enter_exit(credentials):
    t = HTTPTransport(credentials, "https://pvt.whitson.com")
    with t as transport:
        assert transport is t

import logging

import httpx2
import pytest

from whitson_pvt_sdk.errors import (
    APIError,
    AuthError,
    NoResponseError,
    NotFoundError,
    RateLimitError,
    RequestRefusedError,
    ValidationError,
)
from whitson_pvt_sdk.http import HTTPTransport


@pytest.fixture
def recorded_sleeps(monkeypatch):
    sleeps = []
    monkeypatch.setattr("whitson_pvt_sdk.http.time.sleep", sleeps.append)
    return sleeps


def test_strips_trailing_slash_from_base_url(credential, httpx2_mock):
    httpx2_mock.add_response(url="https://dev.pvt.whitson.com/external/v2/test", json={})
    t = HTTPTransport(credential, "https://dev.pvt.whitson.com/")
    t.get("/test")
    req = httpx2_mock.get_requests()[-1]
    assert str(req.url) == "https://dev.pvt.whitson.com/external/v2/test"


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (400, ValidationError),
        (401, AuthError),
        (403, AuthError),
        (404, NotFoundError),
        (409, RequestRefusedError),
        (422, ValidationError),
    ],
)
def test_error_status_raises_its_error_with_the_response(transport, httpx2_mock, status, error):
    httpx2_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/test",
        status_code=status,
        headers={"x-request-id": "req-1"},
        json={"message": "Refused", "import_session_id": 7},
    )
    with pytest.raises(error, match="Refused") as exc:
        transport.get("/test")
    assert type(exc.value) is error
    assert exc.value.status_code == status
    assert exc.value.request_id == "req-1"
    assert exc.value.response_body == {"message": "Refused", "import_session_id": 7}


def test_422_reports_every_validation_error_detail(transport, httpx2_mock, caplog):
    body = {
        "errors": [
            {"field": "MSS -> gor_unit", "message": "Not a GOR unit", "value": "sm3/sm3"},
            {"field": "", "message": "Root error."},
        ]
    }
    httpx2_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/test",
        status_code=422,
        json=body,
    )

    with (
        caplog.at_level(logging.WARNING, logger="whitson_pvt_sdk"),
        pytest.raises(ValidationError) as exc,
    ):
        transport.get("/test")

    expected = (
        "Validation Error: [{'field': 'MSS -> gor_unit', 'message': 'Not a GOR unit', "
        "'value': 'sm3/sm3'}, {'field': '', 'message': 'Root error.'}]"
    )
    assert str(exc.value) == expected
    assert expected in caplog.text
    assert exc.value.response_body == body


@pytest.mark.usefixtures("no_retry_sleep")
def test_get_retries_500_then_succeeds(transport, httpx2_mock):
    url = "https://dev.pvt.whitson.com/external/v2/test"
    httpx2_mock.add_response(url=url, status_code=500, json={"message": "Try again"})
    httpx2_mock.add_response(url=url, json={"ok": True})

    assert transport.get("/test") == {"ok": True}
    assert len(httpx2_mock.get_requests(url=url)) == 2


def test_post_retries_429_then_succeeds(transport, httpx2_mock, recorded_sleeps):
    url = "https://dev.pvt.whitson.com/external/v2/test"
    httpx2_mock.add_response(
        method="POST",
        url=url,
        status_code=429,
        headers={"retry-after": "0"},
        json={"message": "Too many requests"},
    )
    httpx2_mock.add_response(method="POST", url=url, json={"ok": True})

    assert transport.post("/test", body={"name": "test"}) == {"ok": True}
    assert len(httpx2_mock.get_requests(url=url)) == 2
    assert recorded_sleeps == [0]


@pytest.mark.parametrize(
    ("status", "headers", "delay"),
    [
        (429, {"retry-after-ms": "1500"}, 1.5),
        (429, {"retry-after": "Tue, 14 Nov 2023 22:13:25 GMT"}, 5),
        (429, {"x-ratelimit-reset": "1700000007"}, 7),
        (503, {"x-ratelimit-reset": "1700000007"}, pytest.approx(0.25, abs=0.05)),
        (503, {"retry-after": "3"}, 3),
        (429, {"retry-after": "86400"}, 60),
        (429, {"retry-after-ms": "inf", "retry-after": "4"}, 4),
        (429, {"retry-after": "nan"}, pytest.approx(0.25, abs=0.05)),
        (429, {"retry-after": "-5"}, pytest.approx(0.25, abs=0.05)),
        (429, {"x-ratelimit-reset": "inf"}, pytest.approx(0.25, abs=0.05)),
    ],
    ids=[
        "retry-after-ms",
        "http-date",
        "rate-limit-reset",
        "rate-limit-reset-ignored-for-503",
        "retry-after-for-503",
        "capped",
        "infinite-is-absent",
        "nan-is-absent",
        "negative-is-absent",
        "infinite-reset-is-absent",
    ],
)
def test_retry_waits_as_the_response_says(
    transport, httpx2_mock, monkeypatch, recorded_sleeps, status, headers, delay
):
    monkeypatch.setattr("whitson_pvt_sdk._retry.time.time", lambda: 1_700_000_000)
    url = "https://dev.pvt.whitson.com/external/v2/test"
    httpx2_mock.add_response(
        url=url, status_code=status, headers=headers, json={"message": "Try again"}
    )
    httpx2_mock.add_response(url=url, json={"ok": True})

    assert transport.get("/test") == {"ok": True}
    assert recorded_sleeps == [delay]


@pytest.mark.usefixtures("no_retry_sleep")
def test_get_retries_timeout_then_succeeds(transport, httpx2_mock):
    url = "https://dev.pvt.whitson.com/external/v2/test"
    httpx2_mock.add_exception(httpx2.TimeoutException("Timed out"), url=url)
    httpx2_mock.add_response(url=url, json={"ok": True})

    assert transport.get("/test") == {"ok": True}
    assert len(httpx2_mock.get_requests(url=url)) == 2


@pytest.mark.usefixtures("no_retry_sleep")
def test_get_final_timeout_raises_no_response_error(transport, httpx2_mock):
    url = "https://dev.pvt.whitson.com/external/v2/test"
    for _ in range(3):
        httpx2_mock.add_exception(httpx2.ConnectTimeout("Timed out"), url=url)

    with pytest.raises(NoResponseError, match="Timed out"):
        transport.get("/test")

    assert len(httpx2_mock.get_requests(url=url)) == 3


@pytest.mark.usefixtures("no_retry_sleep")
def test_get_final_retryable_status_raises_api_error(transport, httpx2_mock):
    url = "https://dev.pvt.whitson.com/external/v2/test"
    for _ in range(3):
        httpx2_mock.add_response(url=url, status_code=503, json={"message": "Unavailable"})

    with pytest.raises(APIError, match="Unavailable") as exc:
        transport.get("/test")

    assert exc.value.status_code == 503
    assert len(httpx2_mock.get_requests(url=url)) == 3


@pytest.mark.usefixtures("no_retry_sleep")
def test_final_429_raises_rate_limit_error(transport, httpx2_mock):
    url = "https://dev.pvt.whitson.com/external/v2/test"
    for _ in range(3):
        httpx2_mock.add_response(
            url=url,
            status_code=429,
            headers={"retry-after": "2"},
            json={"message": "Too many requests"},
        )

    with pytest.raises(RateLimitError, match="Too many requests") as exc:
        transport.get("/test")

    assert exc.value.status_code == 429
    assert exc.value.retry_after_seconds == 2
    assert len(httpx2_mock.get_requests(url=url)) == 3


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
@pytest.mark.usefixtures("no_retry_sleep")
def test_writes_do_not_retry_500_by_default(transport, httpx2_mock, method):
    url = "https://dev.pvt.whitson.com/external/v2/test"
    httpx2_mock.add_response(
        method=method.upper(), url=url, status_code=500, json={"message": "Internal error"}
    )

    with pytest.raises(APIError, match="Internal error") as exc:
        getattr(transport, method)("/test")

    assert exc.value.status_code == 500
    assert len(httpx2_mock.get_requests(url=url)) == 1


@pytest.mark.usefixtures("no_retry_sleep")
def test_get_bytes_retries_502_then_succeeds(transport, httpx2_mock):
    url = "https://dev.pvt.whitson.com/external/v2/reports/1/export"
    httpx2_mock.add_response(url=url, status_code=502, text="Bad gateway")
    httpx2_mock.add_response(url=url, content=b"binary-data")

    assert transport.get_bytes("/reports/1/export") == b"binary-data"
    assert len(httpx2_mock.get_requests(url=url)) == 2


def test_uses_response_text_when_no_message_field(transport, httpx2_mock):
    httpx2_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/test",
        status_code=400,
        text="plain text error",
    )
    with pytest.raises(ValidationError, match="plain text error"):
        transport.get("/test")


@pytest.mark.usefixtures("no_retry_sleep")
def test_falls_back_to_http_code_when_body_empty(transport, httpx2_mock):
    for _ in range(3):
        httpx2_mock.add_response(
            url="https://dev.pvt.whitson.com/external/v2/test",
            status_code=502,
            content=b"",
        )
    with pytest.raises(APIError, match="HTTP 502") as exc:
        transport.get("/test")
    assert exc.value.status_code == 502

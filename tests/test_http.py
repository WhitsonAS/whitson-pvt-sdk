import logging

import httpx2
import pytest

from whitson_pvt_sdk.errors import (
    APIError,
    AuthError,
    NoResponseError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from whitson_pvt_sdk.http import HTTPTransport
from whitson_pvt_sdk.shared.models import RetryConfig


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


def test_get_returns_parsed_json(transport, httpx2_mock):
    httpx2_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/regions",
        json={"regions": []},
    )
    result = transport.get("/regions")
    assert result == {"regions": []}


def test_get_passes_query_params(transport, httpx2_mock):
    httpx2_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/regions?cursor=abc",
        json={},
    )
    transport.get("/regions", params={"cursor": "abc"})
    req = httpx2_mock.get_requests()[-1]
    assert req.url.query == b"cursor=abc"


def test_post_sends_json_body(transport, httpx2_mock):
    httpx2_mock.add_response(
        method="POST", url="https://dev.pvt.whitson.com/external/v2/regions", json={"id": 1}
    )
    result = transport.post("/regions", body={"name": "test"})
    assert result == {"id": 1}
    body = httpx2_mock.get_requests()[-1].read().decode()
    assert '"name"' in body


def test_put_sends_json_body(transport, httpx2_mock):
    httpx2_mock.add_response(
        method="PUT", url="https://dev.pvt.whitson.com/external/v2/regions/1", json={"id": 1}
    )
    result = transport.put("/regions/1", body={"name": "updated"})
    assert result == {"id": 1}


def test_patch_sends_json_body(transport, httpx2_mock):
    httpx2_mock.add_response(method="PATCH", json={"status": "accepted"})
    assert transport.patch("/resolution", body={"status": "accepted"}) == {"status": "accepted"}


def test_delete_accepts_empty_204(transport, httpx2_mock):
    httpx2_mock.add_response(method="DELETE", status_code=204)
    assert transport.delete("/import-sessions/7") is None


@pytest.mark.parametrize("method", ["patch", "delete"])
@pytest.mark.parametrize(
    "status,error", [(403, AuthError), (404, NotFoundError), (409, APIError), (500, APIError)]
)
def test_new_write_methods_propagate_errors_without_retry(
    transport, httpx2_mock, method, status, error
):
    httpx2_mock.add_response(method=method.upper(), status_code=status, json={"message": "failed"})
    with pytest.raises(error) as exc:
        getattr(transport, method)("/test")
    assert exc.value.status_code == status
    assert len([req for req in httpx2_mock.get_requests() if req.method == method.upper()]) == 1


def test_get_bytes_returns_raw_bytes(transport, httpx2_mock):
    httpx2_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/reports/1/export",
        content=b"binary-data",
    )
    result = transport.get_bytes("/reports/1/export")
    assert result == b"binary-data"


def test_post_multipart_sends_files_and_data(transport, httpx2_mock):
    httpx2_mock.add_response(
        method="POST",
        url="https://dev.pvt.whitson.com/external/v2/reports/import",
        json={"ok": True},
    )
    result = transport.post_multipart(
        "/reports/import",
        files={"file": ("archive.zip", b"data", "application/zip")},
        data={"meta_data": '{"region_id": 1}'},
    )
    assert result == {"ok": True}


def test_401_raises_auth_error(transport, httpx2_mock):
    httpx2_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/test",
        status_code=401,
        headers={"x-request-id": "req-auth"},
        json={"message": "Unauthorized"},
    )
    with pytest.raises(AuthError, match="Unauthorized") as exc:
        transport.get("/test")
    assert exc.value.status_code == 401
    assert exc.value.request_id == "req-auth"
    assert exc.value.response_body == {"message": "Unauthorized"}


def test_403_raises_auth_error(transport, httpx2_mock):
    httpx2_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/test",
        status_code=403,
        json={"message": "Forbidden"},
    )
    with pytest.raises(AuthError, match="Forbidden"):
        transport.get("/test")


def test_404_raises_not_found_error(transport, httpx2_mock):
    httpx2_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/test",
        status_code=404,
        headers={"x-request-id": "req-not-found"},
        json={"message": "Not found"},
    )
    with pytest.raises(NotFoundError, match="Not found") as exc:
        transport.get("/test")
    assert exc.value.status_code == 404
    assert exc.value.request_id == "req-not-found"
    assert exc.value.response_body == {"message": "Not found"}


def test_400_raises_validation_error(transport, httpx2_mock):
    httpx2_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/test",
        status_code=400,
        headers={"x-request-id": "req-validation"},
        json={"message": "Bad request"},
    )
    with pytest.raises(ValidationError, match="Bad request") as exc:
        transport.get("/test")
    assert exc.value.status_code == 400
    assert exc.value.request_id == "req-validation"
    assert exc.value.response_body == {"message": "Bad request"}


def test_422_raises_validation_error(transport, httpx2_mock):
    httpx2_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/test",
        status_code=422,
        json={"message": "Validation failed"},
    )
    with pytest.raises(ValidationError, match="Validation failed"):
        transport.get("/test")


def test_422_formats_validation_error_details(transport, httpx2_mock):
    body = {
        "errors": [
            {"field": "sampling_date", "message": "Not a valid date."},
        ]
    }
    httpx2_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/test",
        status_code=422,
        json=body,
    )

    with pytest.raises(ValidationError, match="Validation Error") as exc:
        transport.get("/test")

    assert (
        str(exc.value)
        == "Validation Error: [{'field': 'sampling_date', 'message': 'Not a valid date.'}]"
    )
    assert exc.value.response_body == body


def test_422_formats_validation_error_detail_values(transport, httpx2_mock, caplog):
    body = {
        "errors": [
            {
                "field": "MSS -> gor_unit",
                "message": "Input should be a canonical stock-tank GOR unit",
                "value": "sm3/sm3",
            },
        ]
    }
    httpx2_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/test",
        status_code=422,
        json=body,
    )

    with caplog.at_level(logging.WARNING, logger="whitson_pvt_sdk"):
        with pytest.raises(ValidationError) as exc:
            transport.get("/test")

    expected = f"Validation Error: {body['errors']}"
    assert str(exc.value) == expected
    assert expected in caplog.text


def test_422_groups_multiple_validation_error_details(transport, httpx2_mock):
    httpx2_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/test",
        status_code=422,
        json={
            "errors": [
                {"field": "sampling_date", "message": "Not a valid date."},
                {"field": "sampling_date", "message": "Date cannot be in the future."},
                {"field": "fluid_model_id", "message": "Field required."},
                {"field": "", "message": "Root error."},
            ]
        },
    )

    with pytest.raises(ValidationError) as exc:
        transport.get("/test")

    assert str(exc.value) == (
        "Validation Error: [{'field': 'sampling_date', 'message': 'Not a valid date.'}, "
        "{'field': 'sampling_date', 'message': 'Date cannot be in the future.'}, "
        "{'field': 'fluid_model_id', 'message': 'Field required.'}, "
        "{'field': '', 'message': 'Root error.'}]"
    )


@pytest.mark.usefixtures("no_retry_sleep")
def test_500_raises_api_error_with_status_code(transport, httpx2_mock):
    for _ in range(3):
        httpx2_mock.add_response(
            url="https://dev.pvt.whitson.com/external/v2/test",
            status_code=500,
            headers={"x-request-id": "req-api"},
            json={"message": "Internal error"},
        )
    with pytest.raises(APIError, match="Internal error") as exc:
        transport.get("/test")
    assert exc.value.status_code == 500
    assert exc.value.request_id == "req-api"
    assert exc.value.response_body == {"message": "Internal error"}


@pytest.mark.usefixtures("no_retry_sleep")
def test_get_retries_500_then_succeeds(transport, httpx2_mock):
    url = "https://dev.pvt.whitson.com/external/v2/test"
    httpx2_mock.add_response(url=url, status_code=500, json={"message": "Try again"})
    httpx2_mock.add_response(url=url, json={"ok": True})

    assert transport.get("/test") == {"ok": True}
    assert len(httpx2_mock.get_requests(url=url)) == 2


def test_get_retries_429_then_succeeds(transport, httpx2_mock, recorded_sleeps):
    url = "https://dev.pvt.whitson.com/external/v2/test"
    httpx2_mock.add_response(
        url=url,
        status_code=429,
        headers={"retry-after": "0"},
        json={"message": "Too many requests"},
    )
    httpx2_mock.add_response(url=url, json={"ok": True})

    assert transport.get("/test") == {"ok": True}
    assert len(httpx2_mock.get_requests(url=url)) == 2
    assert recorded_sleeps == [0]


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


def test_retry_logs_debug_message(transport, httpx2_mock, recorded_sleeps, caplog):
    caplog.set_level(logging.DEBUG, logger="whitson_pvt_sdk")
    url = "https://dev.pvt.whitson.com/external/v2/test"
    httpx2_mock.add_response(
        url=url,
        status_code=429,
        headers={"retry-after": "0"},
        json={"message": "Too many requests"},
    )
    httpx2_mock.add_response(url=url, json={"ok": True})

    assert transport.get("/test") == {"ok": True}
    assert recorded_sleeps == [0]
    assert "Retrying API request" in caplog.text
    assert "GET" in caplog.text
    assert "/test" in caplog.text


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


@pytest.mark.usefixtures("no_retry_sleep")
def test_post_does_not_retry_500_by_default(transport, httpx2_mock):
    url = "https://dev.pvt.whitson.com/external/v2/test"
    httpx2_mock.add_response(
        method="POST", url=url, status_code=500, json={"message": "Internal error"}
    )

    with pytest.raises(APIError, match="Internal error") as exc:
        transport.post("/test", body={"name": "test"})

    assert exc.value.status_code == 500
    assert len(httpx2_mock.get_requests(url=url)) == 1


@pytest.mark.usefixtures("no_retry_sleep")
def test_get_bytes_retries_502_then_succeeds(transport, httpx2_mock):
    url = "https://dev.pvt.whitson.com/external/v2/reports/1/export"
    httpx2_mock.add_response(url=url, status_code=502, text="Bad gateway")
    httpx2_mock.add_response(url=url, content=b"binary-data")

    assert transport.get_bytes("/reports/1/export") == b"binary-data"
    assert len(httpx2_mock.get_requests(url=url)) == 2


@pytest.mark.usefixtures("no_retry_sleep")
def test_retry_config_max_attempts_one_disables_retries(credential, base_url, httpx2_mock):
    transport = HTTPTransport(credential, base_url, retry_config=RetryConfig(max_attempts=1))
    url = "https://dev.pvt.whitson.com/external/v2/test"
    httpx2_mock.add_response(url=url, status_code=503, json={"message": "Unavailable"})

    with pytest.raises(APIError, match="Unavailable"):
        transport.get("/test")

    assert len(httpx2_mock.get_requests(url=url)) == 1


def test_file_timeout_configures_download_timeout(credential, base_url, httpx2_mock):
    transport = HTTPTransport(credential, base_url, file_timeout=19.5)
    httpx2_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/reports/1/export",
        content=b"binary-data",
    )

    assert transport.get_bytes("/reports/1/export") == b"binary-data"
    assert httpx2_mock.get_requests()[-1].extensions["timeout"]["read"] == 19.5


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

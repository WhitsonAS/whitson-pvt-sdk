import pytest

from whitson_pvt_sdk.errors import APIError, AuthError, NotFoundError, ValidationError
from whitson_pvt_sdk.http import HTTPTransport
from whitson_pvt_sdk.models.manual import ClientCredentials


def test_strips_trailing_slash_from_base_url(httpx_mock, auth_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/test", json={}
    )
    t = HTTPTransport(
        ClientCredentials(client_id="id", client_secret="secret"),
        "https://pvt.whitson.com/",
        version="v2",
    )
    t.get("/test")
    req = httpx_mock.get_requests()[-1]
    assert str(req.url) == "https://pvt.whitson.com/external/v2/test"


def test_includes_version_in_base_url(httpx_mock, auth_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v1/test", json={}
    )
    t = HTTPTransport(
        ClientCredentials(client_id="id", client_secret="secret"),
        "https://pvt.whitson.com",
        version="v1",
    )
    t.get("/test")
    req = httpx_mock.get_requests()[-1]
    assert str(req.url) == "https://pvt.whitson.com/external/v1/test"


def test_get_returns_parsed_json(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/regions", json={"regions": []}
    )
    result = transport.get("/regions")
    assert result == {"regions": []}


def test_get_passes_query_params(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/regions?cursor=abc", json={}
    )
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
        method="POST", url="https://pvt.whitson.com/external/v2/reports/import",
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


def test_500_raises_api_error_with_status_code(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/test",
        status_code=500,
        json={"message": "Internal error"},
    )
    with pytest.raises(APIError, match="Internal error") as exc:
        transport.get("/test")
    assert exc.value.status_code == 500


def test_uses_response_text_when_no_message_field(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/test",
        status_code=400,
        text="plain text error",
    )
    with pytest.raises(ValidationError, match="plain text error"):
        transport.get("/test")


def test_falls_back_to_http_code_when_body_empty(transport, httpx_mock):
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

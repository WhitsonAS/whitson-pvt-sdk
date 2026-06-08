from typing import Any

import pytest

from whitson_pvt_sdk.http import HTTPTransport
from whitson_pvt_sdk.shared.models import ClientCredentials


@pytest.fixture
def credentials() -> ClientCredentials:
    return ClientCredentials(client_id="test-id", client_secret="test-secret")


@pytest.fixture
def base_url() -> str:
    return "https://pvt.whitson.com"


@pytest.fixture
def auth_mock(httpx_mock: Any) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://whitson.eu.auth0.com/oauth/token",
        json={
            "access_token": "test-token",
            "expires_in": 86400,
            "token_type": "Bearer",
        },
    )


@pytest.fixture
def transport(
    credentials: ClientCredentials, base_url: str, request: pytest.FixtureRequest
) -> HTTPTransport:
    request.getfixturevalue("auth_mock")
    return HTTPTransport(credentials, base_url, version="v2")


@pytest.fixture
def transport_v1(
    credentials: ClientCredentials, base_url: str, request: pytest.FixtureRequest
) -> HTTPTransport:
    request.getfixturevalue("auth_mock")
    return HTTPTransport(credentials, base_url, version="v1")

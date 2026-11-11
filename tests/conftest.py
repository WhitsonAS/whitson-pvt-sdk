import pytest
from pydantic import SecretStr

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.auth import ApiToken
from whitson_pvt_sdk.http import HTTPTransport


@pytest.fixture(autouse=True)
def _no_ambient_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WHITSON_PVT_TOKEN", raising=False)


@pytest.fixture
def credential() -> ApiToken:
    return ApiToken(token=SecretStr("test-token"))


@pytest.fixture
def base_url() -> str:
    return "https://dev.pvt.whitson.com"


@pytest.fixture
def transport(credential: ApiToken, base_url: str) -> HTTPTransport:
    return HTTPTransport(credential, base_url)


@pytest.fixture
def client(base_url: str) -> WhitsonPVTClient:
    return WhitsonPVTClient(token="test-token", base_url=base_url)

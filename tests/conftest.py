from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypedDict, Unpack
from urllib.parse import parse_qs

import httpx2
import keyring
import pytest
from keyring.backends import fail
from pydantic import SecretStr

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk._store import CredentialStore
from whitson_pvt_sdk.credentials import ApiToken, StoredLogin
from whitson_pvt_sdk.http import HTTPTransport

ISSUER = "https://whitson.eu.auth0.com/"
TOKEN_ENDPOINT = "https://whitson.eu.auth0.com/oauth/token"
DISCOVERY = f"{ISSUER}.well-known/openid-configuration"

EMPTY_PAGE = {"regions": [], "pagination": {"next_cursor": None, "prev_cursor": None}}

StoreLogin = Callable[..., StoredLogin]


class LoginFields(TypedDict, total=False):
    access: str
    refresh: str
    expires_in: timedelta
    audience: str
    token_endpoint: str


def form(request: httpx2.Request) -> dict[str, str]:
    return {key: value[0] for key, value in parse_qs(request.content.decode()).items()}


def auth_config(
    issuer: str = ISSUER,
    device_login: bool | None = True,
    audience: str = "https://dev.pvt.whitson.com/mcp",
    scopes: Sequence[str] = ("read:data",),
) -> dict[str, Any]:
    config = {
        "issuer": issuer,
        "client_id": "cli-client",
        "audience": audience,
        "scopes": list(scopes),
    }
    return config if device_login is None else {**config, "device_login": device_login}


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.delenv("WHITSON_PVT_TOKEN", raising=False)
    monkeypatch.delenv("WHITSON_PVT_URL", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "config"))
    previous = keyring.get_keyring()
    keyring.set_keyring(fail.Keyring())
    yield
    keyring.set_keyring(previous)


@pytest.fixture
def no_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("whitson_pvt_sdk.http.time.sleep", lambda _: None)


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


@pytest.fixture
def store() -> CredentialStore:
    return CredentialStore.from_environment()


def make_login(
    base_url: str,
    *,
    access: str = "access-1",
    refresh: str = "refresh-1",
    expires_in: timedelta = timedelta(hours=1),
    audience: str = "https://dev.pvt.whitson.com/mcp",
    token_endpoint: str = TOKEN_ENDPOINT,
) -> StoredLogin:
    return StoredLogin(
        base_url=base_url,
        issuer=ISSUER,
        client_id="cli-client",
        audience=audience,
        scopes=("read:data",),
        token_endpoint=token_endpoint,
        access_token=SecretStr(access),
        refresh_token=SecretStr(refresh),
        expires_at=datetime.now(UTC) + expires_in,
    )


@pytest.fixture
def store_login(store: CredentialStore) -> StoreLogin:
    def save(base_url: str, **fields: Unpack[LoginFields]) -> StoredLogin:
        login = make_login(base_url, **fields)
        with store.transaction() as transaction:
            transaction.put(login)
            transaction.set_default(login.base_url)
        return login

    return save

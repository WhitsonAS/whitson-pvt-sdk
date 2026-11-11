from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import keyring
import pytest
from keyring.backends import fail
from pydantic import SecretStr

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk._store import CredentialStore
from whitson_pvt_sdk.credentials import ApiToken, StoredLogin
from whitson_pvt_sdk.http import HTTPTransport

ISSUER = "https://login.example.com/"
TOKEN_ENDPOINT = "https://login.example.com/oauth/token"

StoreLogin = Callable[..., StoredLogin]


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
) -> StoredLogin:
    return StoredLogin(
        base_url=base_url,
        issuer=ISSUER,
        client_id="cli-client",
        audience="https://dev.pvt.whitson.com/external",
        scopes=("read:data",),
        token_endpoint=TOKEN_ENDPOINT,
        access_token=SecretStr(access),
        refresh_token=SecretStr(refresh),
        expires_at=datetime.now(timezone.utc) + expires_in,
    )


@pytest.fixture
def store_login(store: CredentialStore) -> StoreLogin:
    def save(
        base_url: str,
        *,
        access: str = "access-1",
        refresh: str = "refresh-1",
        expires_in: timedelta = timedelta(hours=1),
    ) -> StoredLogin:
        login = make_login(base_url, access=access, refresh=refresh, expires_in=expires_in)
        with store.transaction() as transaction:
            transaction.put(login)
            transaction.set_default(login.base_url)
        return login

    return save

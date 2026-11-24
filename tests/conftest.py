import re
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypedDict, Unpack
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx2
import keyring
import pytest
from keyring.backends import fail
from pydantic import BaseModel, ConfigDict, SecretStr

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk._store import ActiveLogin, CredentialStore
from whitson_pvt_sdk.credentials import ApiToken, StoredLogin
from whitson_pvt_sdk.http import HTTPTransport

ISSUER = "https://whitson.eu.auth0.com/"
TOKEN_ENDPOINT = "https://whitson.eu.auth0.com/oauth/token"
DISCOVERY = f"{ISSUER}.well-known/openid-configuration"
AUTHORIZE = f"{ISSUER}authorize"
DEVICE_ENDPOINT = f"{ISSUER}oauth/device/code"
PROVIDER = {
    "issuer": ISSUER,
    "authorization_endpoint": AUTHORIZE,
    "token_endpoint": TOKEN_ENDPOINT,
    "device_authorization_endpoint": DEVICE_ENDPOINT,
}
ROLE_NOT_CONFIRMED = (
    "Your whitsonPVT role has not been confirmed in the last 30 days; sign in to the whitsonPVT "
    "web app, then try again"
)
NAMELESS_WELL = {
    f"{name}_name": None
    for name in ("basin", "field", "field_segment", "formation", "formation_zone", "sub_basin")
}

EMPTY_PAGE = {"regions": [], "pagination": {"next_cursor": None, "prev_cursor": None}}

StoreLogin = Callable[..., StoredLogin]


class LoginFields(TypedDict, total=False):
    access: str
    refresh: str
    expires_in: timedelta
    audience: str
    token_endpoint: str
    client_id: str


def form(request: httpx2.Request) -> dict[str, str]:
    return {key: value[0] for key, value in parse_qs(request.content.decode()).items()}


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


_BROWSER = urllib.request.build_opener(_NoRedirects)


class PageResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: int
    location: str | None
    headers: dict[str, str]
    body: str

    @property
    def outcome(self) -> tuple[int, str | None]:
        heading = re.search(r"<h1>(.*?)</h1>", self.body)
        return self.status, None if heading is None else heading[1]


def open_page(request: str | urllib.request.Request) -> PageResponse:
    try:
        with _BROWSER.open(request, timeout=5) as response:
            status, headers, body = response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        with error:
            status, headers, body = error.code, error.headers, error.read()
    return PageResponse(
        status=status, location=headers.get("Location"), headers=dict(headers), body=body.decode()
    )


def post_form(url: str, fields: list[tuple[str, str]]) -> PageResponse:
    return open_page(urllib.request.Request(url, data=urlencode(fields).encode(), method="POST"))


def query_params(url: str) -> dict[str, str]:
    return {key: value[0] for key, value in parse_qs(urlsplit(url).query).items()}


def auth_config(
    issuer: str = ISSUER,
    audience: str = "https://dev.pvt.whitson.com/mcp",
    scopes: Sequence[str] = ("read:data",),
    connection: str | None = None,
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "issuer": issuer,
        "client_id": "cli-client",
        "audience": audience,
        "scopes": list(scopes),
    }
    if connection is not None:
        config["connection"] = connection
    return config


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
    client_id: str = "cli-client",
) -> StoredLogin:
    return StoredLogin(
        base_url=base_url,
        issuer=ISSUER,
        client_id=client_id,
        audience=audience,
        scopes=("read:data",),
        token_endpoint=token_endpoint,
        access_token=SecretStr(access),
        refresh_token=SecretStr(refresh),
        expires_at=datetime.now(UTC) + expires_in,
    )


def active_login(store: CredentialStore, base_url: str) -> StoredLogin:
    entry = store.get(base_url)
    assert isinstance(entry, ActiveLogin)
    return entry.login


@pytest.fixture
def store_login(store: CredentialStore) -> StoreLogin:
    def save(base_url: str, **fields: Unpack[LoginFields]) -> StoredLogin:
        login = make_login(base_url, **fields)
        with store.transaction() as transaction:
            transaction.put(login)
            transaction.set_default(login.base_url)
        return login

    return save

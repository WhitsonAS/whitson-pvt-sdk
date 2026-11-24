import os
from collections.abc import Generator, MutableMapping
from typing import Literal

import httpx2
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from whitson_pvt_sdk._refresh import (
    NoLongerValid,
    RefreshOutcome,
    Usable,
    replace_access_token,
)
from whitson_pvt_sdk._store import ActiveLogin, CredentialStore, InvalidLogin
from whitson_pvt_sdk._trust import is_secure_url
from whitson_pvt_sdk.credentials import (
    ApiToken,
    Credential,
    StoredLogin,
    normalise_url,
    origin,
    same_origin,
)
from whitson_pvt_sdk.errors import ConfigurationError, LoginError

TOKEN_ENV_VAR = "WHITSON_PVT_TOKEN"
URL_ENV_VAR = "WHITSON_PVT_URL"


class FromArgument(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: Literal["argument"] = "argument"
    url: str
    credential: ApiToken


class FromEnvironment(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: Literal["environment"] = "environment"
    url: str
    credential: ApiToken


class FromStore(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: Literal["store"] = "store"
    url: str
    credential: StoredLogin


ResolvedCredential = FromArgument | FromEnvironment | FromStore


class UrlFromArgument(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str


class UrlFromEnvironment(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str


class UrlFromDefaultLogin(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str


ResolvedUrl = UrlFromArgument | UrlFromEnvironment | UrlFromDefaultLogin


def resolve_base_url(base_url: str | None) -> ResolvedUrl:
    if base_url is not None:
        return UrlFromArgument(url=_url(base_url, "The base_url argument"))
    env_url = os.environ.get(URL_ENV_VAR)
    if env_url is not None:
        return UrlFromEnvironment(url=_url(env_url, URL_ENV_VAR))
    default = CredentialStore.from_environment().default_url()
    if default is not None:
        return UrlFromDefaultLogin(url=default)
    raise ConfigurationError(
        "No deployment URL configured. Provide one of: the base_url argument (--url on "
        f"wpvt auth and wpvt mcp), the {URL_ENV_VAR} environment variable, or a default login from "
        "`wpvt auth login --url <url>`."
    )


def resolve_credential(base_url: str | None, token: str | None) -> ResolvedCredential:
    deployment = resolve_base_url(base_url)
    url = deployment.url
    given = _given_api_token(url, token)
    if given is None:
        return FromStore(url=url, credential=_stored_login(url))
    match deployment:
        case UrlFromDefaultLogin():
            given_by = (
                "The token= argument was given"
                if isinstance(given, FromArgument)
                else f"{TOKEN_ENV_VAR} is set"
            )
            raise ConfigurationError(
                f"{given_by} without a deployment URL, so the URL would come from the default "
                f"login ({url}). An API token is only sent to a URL given explicitly: set "
                f"{URL_ENV_VAR} (or base_url=, or --url on wpvt auth and wpvt mcp), or drop the "
                "token to use the login."
            )
        case UrlFromArgument() | UrlFromEnvironment():
            if not is_secure_url(url):
                raise ConfigurationError(
                    f"Refusing to send an API token over plain HTTP to {url}; use https:// "
                    "(http only for this machine, such as http://localhost)."
                )
            return given


def _given_api_token(url: str, token: str | None) -> FromArgument | FromEnvironment | None:
    if token is not None:
        return FromArgument(url=url, credential=_api_token(token, "The token= argument is empty"))
    env_token = os.environ.get(TOKEN_ENV_VAR)
    if env_token is not None:
        return FromEnvironment(
            url=url, credential=_api_token(env_token, f"{TOKEN_ENV_VAR} is set but empty")
        )
    return None


def _stored_login(base_url: str) -> StoredLogin:
    match CredentialStore.from_environment().get(base_url):
        case ActiveLogin(login=login):
            return login
        case InvalidLogin(reason=reason):
            raise _login_invalid(base_url, reason)
        case None:
            raise ConfigurationError(
                f"No credentials configured for {base_url}. Provide one of: the token= "
                f"argument, the {TOKEN_ENV_VAR} environment variable, or a stored login from "
                f"`wpvt auth login --url {base_url}`."
            )


def _url(value: str, source: str) -> str:
    if not value.strip():
        raise ConfigurationError(f"{source} is set but empty")
    try:
        return normalise_url(value)
    except ValueError:
        raise ConfigurationError(
            f"{source} must be an http(s) URL such as https://example.pvt.whitson.com"
        ) from None


def _api_token(value: str, empty_message: str) -> ApiToken:
    try:
        return ApiToken(token=SecretStr(value))
    except ValidationError:
        raise ConfigurationError(empty_message) from None


def _login_invalid(base_url: str, reason: str) -> LoginError:
    return LoginError(
        f"The stored login for {base_url} is no longer valid: {reason}. "
        f"Run `wpvt auth login --url {base_url}`."
    )


class BearerSource:
    def __init__(self, credential: Credential) -> None:
        self._credential: Credential = credential
        self._store = CredentialStore.from_environment()

    def current(self, url: str | httpx2.URL) -> SecretStr:
        match self._credential:
            case ApiToken() as api_token:
                return api_token.token
            case StoredLogin() as login:
                if not same_origin(url, login.base_url):
                    raise ConfigurationError(
                        f"Refusing to send the stored login for {login.base_url} to {origin(url)}."
                    )
                if login.expiring():
                    login = self._adopt(replace_access_token(login, self._store))
                return login.access_token

    def renewed_after_rejection(self) -> SecretStr | None:
        match self._credential:
            case ApiToken():
                return None
            case StoredLogin() as login:
                return self._adopt(replace_access_token(login, self._store)).access_token

    def _adopt(self, outcome: RefreshOutcome) -> StoredLogin:
        match outcome:
            case Usable(login=login):
                self._credential = login
                return login
            case NoLongerValid(base_url=base_url, reason=reason):
                raise _login_invalid(base_url, reason)


class CredentialAuth(httpx2.Auth):
    def __init__(self, credential: Credential) -> None:
        self._bearer = BearerSource(credential)
        self.requires_request_body = isinstance(credential, StoredLogin)

    def auth_flow(
        self, request: httpx2.Request
    ) -> Generator[httpx2.Request, httpx2.Response, None]:
        set_bearer(request.headers, self._bearer.current(request.url))
        response = yield request
        if response.status_code == 401:
            renewed = self._bearer.renewed_after_rejection()
            if renewed is not None:
                set_bearer(request.headers, renewed)
                yield request


def set_bearer(headers: MutableMapping[str, str], token: SecretStr) -> None:
    headers["Authorization"] = f"Bearer {token.get_secret_value()}"

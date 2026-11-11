import os
from collections.abc import Generator
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr, TypeAdapter, ValidationError

from whitson_pvt_sdk._refresh import (
    NoLongerValid,
    Refreshed,
    RefreshOutcome,
    StillValid,
    replace_access_token,
    usable_login,
)
from whitson_pvt_sdk._store import ActiveLogin, CredentialStore, InvalidLogin
from whitson_pvt_sdk.credentials import (
    ApiToken,
    Credential,
    DeploymentUrl,
    StoredLogin,
    same_origin,
)
from whitson_pvt_sdk.errors import ConfigurationError, LoginError

TOKEN_ENV_VAR = "WHITSON_PVT_TOKEN"
URL_ENV_VAR = "WHITSON_PVT_URL"

_deployment_url: TypeAdapter[str] = TypeAdapter(DeploymentUrl)


class FromArgument(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: Literal["argument"] = "argument"
    credential: ApiToken


class FromEnvironment(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: Literal["environment"] = "environment"
    credential: ApiToken


class FromStore(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: Literal["store"] = "store"
    credential: StoredLogin


ResolvedCredential = FromArgument | FromEnvironment | FromStore


def resolve_base_url(base_url: str | None) -> str:
    if base_url is not None:
        return _url(base_url, "The base_url argument")
    env_url = os.environ.get(URL_ENV_VAR)
    if env_url is not None:
        return _url(env_url, URL_ENV_VAR)
    default = CredentialStore.from_environment().default_url()
    if default is not None:
        return default
    raise ConfigurationError(
        "No deployment URL configured. Provide one of: the base_url argument (--url), "
        f"the {URL_ENV_VAR} environment variable, or a default login from "
        "`wpvt auth login --url <url>`."
    )


def resolve_credential(base_url: str, token: str | None) -> ResolvedCredential:
    if token is not None:
        return FromArgument(credential=_api_token(token, "The token= argument is empty"))
    env_token = os.environ.get(TOKEN_ENV_VAR)
    if env_token is not None:
        return FromEnvironment(
            credential=_api_token(env_token, f"{TOKEN_ENV_VAR} is set but empty")
        )
    match CredentialStore.from_environment().get(base_url):
        case ActiveLogin(login=login):
            return FromStore(credential=login)
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
        return _deployment_url.validate_python(value)
    except ValidationError:
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


class CredentialAuth(httpx.Auth):
    requires_request_body = True

    def __init__(self, credential: Credential) -> None:
        self._credential = credential
        self._store = CredentialStore.from_environment()

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        match self._credential:
            case ApiToken(token=token):
                _set_bearer(request, token)
                yield request
            case StoredLogin() as login:
                if not same_origin(request.url, login.base_url):
                    raise ConfigurationError(
                        f"Refusing to send the stored login for {login.base_url} to "
                        f"{request.url.scheme}://{request.url.netloc.decode()}."
                    )
                login = self._adopt(usable_login(login, self._store))
                _set_bearer(request, login.access_token)
                response = yield request
                if response.status_code == 401:
                    login = self._adopt(replace_access_token(login, self._store))
                    _set_bearer(request, login.access_token)
                    yield request

    def _adopt(self, outcome: RefreshOutcome) -> StoredLogin:
        match outcome:
            case StillValid(login=login) | Refreshed(login=login):
                self._credential = login
                return login
            case NoLongerValid(base_url=base_url, reason=reason):
                raise _login_invalid(base_url, reason)


def _set_bearer(request: httpx.Request, token: SecretStr) -> None:
    request.headers["Authorization"] = f"Bearer {token.get_secret_value()}"

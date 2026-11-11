import os
from collections.abc import Generator
from typing import Annotated

import httpx
from pydantic import AfterValidator, BaseModel, ConfigDict, SecretStr, ValidationError

from whitson_pvt_sdk.errors import ConfigurationError

TOKEN_ENV_VAR = "WHITSON_PVT_TOKEN"


def _not_blank(token: SecretStr) -> SecretStr:
    if not token.get_secret_value().strip():
        raise ValueError("token is blank")
    return token


class ApiToken(BaseModel):
    model_config = ConfigDict(frozen=True)

    token: Annotated[SecretStr, AfterValidator(_not_blank)]


def resolve_credential(token: str | None) -> ApiToken:
    if token is not None:
        return _api_token(token, empty_message="The token= argument is empty")
    env_token = os.environ.get(TOKEN_ENV_VAR)
    if env_token is not None:
        return _api_token(env_token, empty_message=f"{TOKEN_ENV_VAR} is set but empty")
    raise ConfigurationError(
        "No credentials configured. Provide one of: the token= argument, "
        f"the {TOKEN_ENV_VAR} environment variable."
    )


def _api_token(value: str, *, empty_message: str) -> ApiToken:
    try:
        return ApiToken(token=SecretStr(value))
    except ValidationError:
        raise ConfigurationError(empty_message) from None


class CredentialAuth(httpx.Auth):
    def __init__(self, credential: ApiToken) -> None:
        self._credential = credential

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        match self._credential:
            case ApiToken(token=token):
                request.headers["Authorization"] = f"Bearer {token.get_secret_value()}"
                yield request

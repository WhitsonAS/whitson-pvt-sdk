from datetime import datetime, timedelta, timezone
from typing import TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic import ValidationError as PydanticValidationError

from whitson_pvt_sdk._trust import SecureUrl
from whitson_pvt_sdk.credentials import StoredLogin, same_origin
from whitson_pvt_sdk.errors import APIError, ConfigurationError, LoginError, NoResponseError

HTTP_TIMEOUT_SECONDS = 30.0

_Model = TypeVar("_Model", bound=BaseModel)


class AuthConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    issuer: SecureUrl
    client_id: str
    audience: str
    scopes: tuple[str, ...]
    connection: str | None = None
    device_login: bool = False


class ProviderMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    issuer: str
    authorization_endpoint: SecureUrl
    token_endpoint: SecureUrl
    device_authorization_endpoint: SecureUrl | None = None
    revocation_endpoint: SecureUrl | None = None


class TokenResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    token_type: str
    access_token: SecretStr
    refresh_token: SecretStr | None = None
    expires_in: int = Field(gt=0)

    @field_validator("token_type")
    @classmethod
    def _bearer(cls, value: str) -> str:
        if value.lower() != "bearer":
            raise ValueError("token_type must be Bearer")
        return value

    def expires_at(self) -> datetime:
        return datetime.now(timezone.utc) + timedelta(seconds=self.expires_in)


class OAuthError(BaseModel):
    model_config = ConfigDict(frozen=True)

    error: str
    error_description: str | None = None

    def describe(self) -> str:
        if self.error_description:
            return f"{self.error}: {self.error_description}"
        return self.error


class TokenGranted(BaseModel):
    model_config = ConfigDict(frozen=True)

    token: TokenResponse


class TokenRefused(BaseModel):
    model_config = ConfigDict(frozen=True)

    error: OAuthError


TokenResult = TokenGranted | TokenRefused


def oauth_client() -> httpx.Client:
    return httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)


def fetch_auth_config(http: httpx.Client, base_url: str) -> AuthConfig:
    response = _send(http, "GET", f"{base_url}/external/v2/auth/config")
    if response.status_code == 404:
        raise ConfigurationError(f"Command-line login is not enabled on {base_url}.")
    return _parse(AuthConfig, response, f"{base_url}/external/v2/auth/config")


def discover(http: httpx.Client, issuer: str) -> ProviderMetadata:
    url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
    metadata = _parse(ProviderMetadata, _send(http, "GET", url), url)
    if metadata.issuer.rstrip("/") != issuer.rstrip("/"):
        raise LoginError(f"{url} describes the issuer {metadata.issuer}, not {issuer}.")
    if not same_origin(metadata.authorization_endpoint, issuer):
        raise LoginError(
            f"{url} sends the browser to {httpx.URL(metadata.authorization_endpoint).host}, "
            f"not to the login server {httpx.URL(issuer).host}; refusing to log in."
        )
    return metadata


def post_form(http: httpx.Client, url: str, form: dict[str, str]) -> httpx.Response:
    return _send(http, "POST", url, data=form)


def request_token(http: httpx.Client, token_endpoint: str, form: dict[str, str]) -> TokenResult:
    response = post_form(http, token_endpoint, form)
    if response.status_code in (400, 401, 403):
        return TokenRefused(error=parse_oauth_error(response, token_endpoint))
    return TokenGranted(token=_parse(TokenResponse, response, token_endpoint))


def parse_oauth_error(response: httpx.Response, url: str) -> OAuthError:
    try:
        return OAuthError.model_validate_json(response.content)
    except PydanticValidationError:
        raise APIError(
            f"{url} answered HTTP {response.status_code} without an OAuth error",
            response.status_code,
        ) from None


def refreshed_login(login: StoredLogin, token: TokenResponse) -> StoredLogin:
    return login.model_copy(
        update={
            "access_token": token.access_token,
            "refresh_token": token.refresh_token or login.refresh_token,
            "expires_at": token.expires_at(),
        }
    )


def revoke_refresh_token(http: httpx.Client, endpoint: str, login: StoredLogin) -> bool:
    response = post_form(
        http,
        endpoint,
        {
            "token": login.refresh_token.get_secret_value(),
            "token_type_hint": "refresh_token",
            "client_id": login.client_id,
        },
    )
    return response.is_success


def _send(
    http: httpx.Client, method: str, url: str, *, data: dict[str, str] | None = None
) -> httpx.Response:
    try:
        return http.request(method, url, data=data, headers={"Accept": "application/json"})
    except httpx.TransportError as exc:
        raise NoResponseError(f"Could not reach {httpx.URL(url).host}: {exc}") from exc


def _parse(model: type[_Model], response: httpx.Response, url: str) -> _Model:
    if not response.is_success:
        raise APIError(f"{url} answered HTTP {response.status_code}", response.status_code)
    try:
        return model.model_validate_json(response.content)
    except PydanticValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(map(str, error['loc']))}: {error['msg']}"
            for error in exc.errors(include_url=False, include_input=False, include_context=False)
        )
        raise LoginError(f"{url} returned a response this SDK cannot use ({problems}).") from None

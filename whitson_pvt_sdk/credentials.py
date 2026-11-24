from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx2
from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, SecretStr

REFRESH_MARGIN = timedelta(minutes=5)


def _not_blank(token: SecretStr) -> SecretStr:
    if not token.get_secret_value().strip():
        raise ValueError("token is blank")
    return token


_NonBlankSecret = Annotated[SecretStr, AfterValidator(_not_blank)]


def normalise_url(value: str) -> str:
    try:
        url = httpx2.URL(value.strip())
    except httpx2.InvalidURL:
        raise ValueError(f"{value!r} is not a URL") from None
    if url.scheme not in ("http", "https") or not url.host:
        raise ValueError(f"{value!r} is not an http(s) URL")
    if url.userinfo or url.query or url.fragment:
        raise ValueError(f"{value!r} must not contain credentials, a query or a fragment")
    host = host_name(url).rstrip(".")
    if "" in host.split("."):
        raise ValueError(f"{value!r} has an empty host name label")
    return origin(url.copy_with(host=host)) + url.path.rstrip("/")


DeploymentUrl = Annotated[str, AfterValidator(normalise_url)]


def host_name(url: str | httpx2.URL) -> str:
    # The IDNA (ASCII) form: httpx2's URL.host shows any punycode label as Unicode.
    return httpx2.URL(url).raw_host.decode("ascii")


def origin(url: str | httpx2.URL) -> str:
    parsed = httpx2.URL(url)
    return f"{parsed.scheme}://{parsed.netloc.decode()}"


def same_origin(a: str | httpx2.URL, b: str | httpx2.URL) -> bool:
    first, second = httpx2.URL(a), httpx2.URL(b)
    return (first.scheme, host_name(first), first.port) == (
        second.scheme,
        host_name(second),
        second.port,
    )


def same_issuer(a: str, b: str) -> bool:
    return a.rstrip("/") == b.rstrip("/")


class ApiToken(BaseModel):
    model_config = ConfigDict(frozen=True)

    token: _NonBlankSecret


class StoredLogin(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_url: DeploymentUrl
    issuer: str
    client_id: str
    audience: str
    scopes: tuple[str, ...]
    token_endpoint: str
    access_token: _NonBlankSecret
    refresh_token: _NonBlankSecret
    expires_at: AwareDatetime

    def expiring(self) -> bool:
        return self.expires_at - REFRESH_MARGIN <= datetime.now(UTC)

    def same_client(self, other: "StoredLogin") -> bool:
        return (self.issuer, self.client_id, self.audience) == (
            other.issuer,
            other.client_id,
            other.audience,
        )


Credential = ApiToken | StoredLogin

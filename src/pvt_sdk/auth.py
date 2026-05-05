import time

import httpx

from .models import ClientCredentials, TokenData
from .errors import AuthError

_MIN_TOKEN_LIFETIME = 300
_DEFAULT_AUTH0_DOMAIN = "whitson.eu.auth0.com"
_DEFAULT_AUDIENCE = "https://pvt.whitson.com/external"


class TokenManager:
    """Manages M2M token exchange and in-memory caching.

    Usage:
        manager = TokenManager(ClientCredentials(client_id="...", client_secret="..."))
        token = manager.get_token()
    """

    def __init__(
        self,
        credentials: ClientCredentials,
        *,
        auth0_domain: str = _DEFAULT_AUTH0_DOMAIN,
        audience: str = _DEFAULT_AUDIENCE,
    ) -> None:
        self._credentials = credentials
        self._auth0_domain = auth0_domain
        self._audience = audience
        self._cached_access_token: str | None = None
        self._cached_expires_at: float = 0.0

    def get_token(self) -> str:
        if (
            self._cached_access_token
            and self._cached_expires_at > time.time() + _MIN_TOKEN_LIFETIME
        ):
            return self._cached_access_token
        return self._exchange()

    def _exchange(self) -> str:
        try:
            resp = httpx.post(
                f"https://{self._auth0_domain}/oauth/token",
                json={
                    "client_id": self._credentials.client_id,
                    "client_secret": self._credentials.client_secret,
                    "audience": self._audience,
                    "grant_type": "client_credentials",
                },
                timeout=10,
            )
            resp.raise_for_status()
            token_data = TokenData.model_validate(resp.json())
            self._cached_access_token = token_data.access_token
            self._cached_expires_at = time.time() + token_data.expires_in
            return self._cached_access_token
        except httpx.TimeoutException as e:
            raise AuthError("Authentication service timeout") from e
        except httpx.HTTPError as e:
            raise AuthError("Authentication service unavailable") from e

import logging
import time

import httpx

from .errors import AuthError
from .shared.models import ClientCredentials, TokenData

_MIN_TOKEN_LIFETIME = 300
logger = logging.getLogger("whitson_pvt_sdk")


class TokenManager:
    """Manages M2M token exchange and in-memory caching.

    Usage:
        manager = TokenManager(
            ClientCredentials(client_id="...", client_secret="..."),
            token_url="https://.../external/v2/auth/token",
        )
        token = manager.get_token()
    """

    def __init__(
        self,
        credentials: ClientCredentials,
        *,
        token_url: str,
    ) -> None:
        self._credentials = credentials
        self._token_url = token_url
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
            logger.debug("Requesting access token")
            resp = httpx.post(
                self._token_url,
                json={
                    "client_id": self._credentials.client_id,
                    "client_secret": self._credentials.client_secret,
                },
                timeout=10,
            )
            resp.raise_for_status()
            token_data = TokenData.model_validate(resp.json())
            self._cached_access_token = token_data.access_token
            self._cached_expires_at = time.time() + token_data.expires_in
            logger.debug("Access token cached: expires_in=%s", token_data.expires_in)
            return self._cached_access_token
        except httpx.TimeoutException as e:
            logger.warning("Authentication request timed out")
            raise AuthError("Authentication service timeout") from e
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                logger.warning(
                    "Authentication service unavailable: status=%s",
                    e.response.status_code,
                )
                raise AuthError(
                    "Authentication service unavailable",
                    status_code=e.response.status_code,
                    response_body=e.response.text,
                    request_id=e.response.headers.get("x-request-id"),
                ) from e
            try:
                body = e.response.json()
                detail = body.get("error_description") or body.get("error") or e.response.text
            except ValueError:
                body = e.response.text
                detail = e.response.text
            logger.warning("Authentication failed: status=%s", e.response.status_code)
            raise AuthError(
                f"Authentication failed: {detail}",
                status_code=e.response.status_code,
                response_body=body,
                request_id=e.response.headers.get("x-request-id"),
            ) from e
        except httpx.HTTPError as e:
            logger.warning("Authentication request failed: error=%s", e)
            raise AuthError("Authentication service unavailable") from e

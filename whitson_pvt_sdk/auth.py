import logging
import threading
import time
from typing import Any

import httpx

from ._retry import retry_delay
from .errors import AuthError
from .shared.models import ClientCredentials, RetryConfig, TokenData

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
        retry_config: RetryConfig | None = None,
    ) -> None:
        self._credentials = credentials
        self._token_url = token_url
        self._retry_config = retry_config or RetryConfig()
        self._cached_access_token: str | None = None
        self._cached_expires_at: float = 0.0
        self._lock = threading.Lock()

    def get_token(self) -> str:
        token = self._valid_cached_token()
        if token is not None:
            return token

        with self._lock:
            token = self._valid_cached_token()
            if token is not None:
                return token
            return self._exchange()

    def _valid_cached_token(self) -> str | None:
        if (
            self._cached_access_token
            and self._cached_expires_at > time.time() + _MIN_TOKEN_LIFETIME
        ):
            return self._cached_access_token
        return None

    def _exchange(self) -> str:
        for attempt in range(1, self._retry_config.max_attempts + 1):
            try:
                logger.debug("Requesting access token: attempt=%s", attempt)
                response = httpx.post(
                    self._token_url,
                    json={
                        "client_id": self._credentials.client_id,
                        "client_secret": self._credentials.client_secret,
                    },
                    timeout=10,
                )
                if self._should_retry_response(response, attempt):
                    self._sleep_before_retry(attempt, response)
                    response.close()
                    continue
                response.raise_for_status()
                token_data = TokenData.model_validate(response.json())
                self._cached_access_token = token_data.access_token
                self._cached_expires_at = time.time() + token_data.expires_in
                logger.debug("Access token cached: expires_in=%s", token_data.expires_in)
                return self._cached_access_token
            except httpx.TimeoutException as e:
                if self._has_attempt_remaining(attempt):
                    self._sleep_before_retry(attempt)
                    continue
                logger.warning("Authentication request timed out")
                raise AuthError("Authentication service timeout") from e
            except httpx.HTTPStatusError as e:
                self._raise_status_error(e)
            except httpx.HTTPError as e:
                if self._has_attempt_remaining(attempt):
                    self._sleep_before_retry(attempt)
                    continue
                logger.warning("Authentication request failed: error=%s", e)
                raise AuthError("Authentication service unavailable") from e

        raise RuntimeError("Authentication retry loop exhausted without returning or raising")

    def _should_retry_response(self, response: httpx.Response, attempt: int) -> bool:
        return (
            self._has_attempt_remaining(attempt)
            and response.status_code in self._retry_config.statuses
        )

    def _has_attempt_remaining(self, attempt: int) -> bool:
        return attempt < self._retry_config.max_attempts

    def _sleep_before_retry(self, attempt: int, response: httpx.Response | None = None) -> None:
        delay = retry_delay(response, self._retry_config, attempt)
        logger.debug(
            "Retrying authentication request: attempt=%s status=%s delay=%.3f",
            attempt,
            response.status_code if response is not None else None,
            delay,
        )
        time.sleep(delay)

    def _raise_status_error(self, error: httpx.HTTPStatusError) -> None:
        response = error.response
        if response.status_code >= 500:
            logger.warning(
                "Authentication service unavailable: status=%s",
                response.status_code,
            )
            raise AuthError(
                "Authentication service unavailable",
                status_code=response.status_code,
                response_body=response.text,
                request_id=response.headers.get("x-request-id"),
            ) from error
        try:
            body: Any = response.json()
            detail = body.get("error_description") or body.get("error") or response.text
        except ValueError:
            body = response.text
            detail = response.text
        logger.warning("Authentication failed: status=%s", response.status_code)
        raise AuthError(
            f"Authentication failed: {detail}",
            status_code=response.status_code,
            response_body=body,
            request_id=response.headers.get("x-request-id"),
        ) from error

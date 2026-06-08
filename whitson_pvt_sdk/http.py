import email.utils
import logging
import random
import time
from types import TracebackType
from typing import Any, TypeAlias

import httpx

from whitson_pvt_sdk.auth import TokenManager
from whitson_pvt_sdk.errors import APIError, AuthError, NotFoundError, ValidationError
from whitson_pvt_sdk.shared.models import ClientCredentials, RetryConfig

logger = logging.getLogger(__name__)

JSONBody: TypeAlias = dict[str, Any] | list[dict[str, Any]] | None

Params: TypeAlias = dict[str, str | int] | None


class _BearerAuth(httpx.Auth):
    def __init__(self, token_manager: TokenManager) -> None:
        self._token_manager = token_manager

    def auth_flow(self, request: httpx.Request) -> Any:
        request.headers["Authorization"] = f"Bearer {self._token_manager.get_token()}"
        yield request


class HTTPTransport:
    def __init__(
        self,
        credentials: ClientCredentials,
        base_url: str,
        *,
        version: str = "v1",
        auth0_domain: str | None = None,
        audience: str | None = None,
        retry_config: RetryConfig | None = None,
        timeout: float = 30.0,
        file_timeout: float = 60.0,
    ) -> None:
        token_kwargs: dict[str, str] = {}
        if auth0_domain:
            token_kwargs["auth0_domain"] = auth0_domain
        if audience:
            token_kwargs["audience"] = audience

        self._token_manager = TokenManager(credentials, **token_kwargs)
        self._retry_config = retry_config or RetryConfig()
        self._file_timeout = file_timeout
        self._http = httpx.Client(
            auth=_BearerAuth(self._token_manager),
            base_url=f"{base_url.rstrip('/')}/external/{version}",
            timeout=timeout,
        )

    def __enter__(self) -> "HTTPTransport":
        self._http.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._http.__exit__(exc_type, exc_value, tb)

    def close(self) -> None:
        self._http.close()

    def get_access_token(self) -> str:
        return self._token_manager.get_token()

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            return response.json().get("message", response.text)
        except Exception:
            return response.text or f"HTTP {response.status_code}"

    @classmethod
    def _raise_for_status(cls, response: httpx.Response) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return
        msg = cls._error_message(response)
        if status in (401, 403):
            raise AuthError(msg)
        if status == 404:
            raise NotFoundError(msg)
        if status in (400, 422):
            raise ValidationError(msg)
        raise APIError(msg, status_code=status)

    def _json(self, response: httpx.Response) -> dict[str, Any]:
        self._raise_for_status(response)
        return response.json()

    def _bytes(self, response: httpx.Response) -> bytes:
        self._raise_for_status(response)
        return response.content

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Params = None,
        json: JSONBody = None,
        files: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        method = method.upper()
        for attempt in range(1, self._retry_config.max_attempts + 1):
            try:
                response = self._http.request(
                    method,
                    path,
                    params=params,
                    json=json,
                    files=files,
                    data=data,
                    timeout=timeout,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if self._should_retry_exception(method, attempt):
                    self._sleep_before_retry(attempt)
                    continue
                raise APIError(f"Request failed: {exc}") from exc

            if self._should_retry_response(method, response, attempt):
                self._sleep_before_retry(attempt, response)
                response.close()
                continue

            return response

        raise RuntimeError("Retry loop exhausted without returning or raising")

    def _should_retry_exception(self, method: str, attempt: int) -> bool:
        return self._is_retryable_method(method) and self._has_attempt_remaining(attempt)

    def _should_retry_response(
        self, method: str, response: httpx.Response, attempt: int
    ) -> bool:
        return (
            self._is_retryable_method(method)
            and self._has_attempt_remaining(attempt)
            and response.status_code in self._retry_config.statuses
        )

    def _is_retryable_method(self, method: str) -> bool:
        return method in self._retry_config.methods

    def _has_attempt_remaining(self, attempt: int) -> bool:
        return attempt < self._retry_config.max_attempts

    def _sleep_before_retry(
        self, attempt: int, response: httpx.Response | None = None
    ) -> None:
        retry_after = self._retry_after(response) if response is not None else None
        if retry_after is None:
            retry_after = min(
                self._retry_config.backoff_factor * (2 ** (attempt - 1)),
                self._retry_config.max_backoff,
            )
            retry_after *= random.uniform(0.8, 1.2)
        time.sleep(retry_after)

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        value = response.headers.get("retry-after-ms")
        if value is not None:
            try:
                return max(float(value) / 1000, 0)
            except ValueError:
                pass

        value = response.headers.get("retry-after")
        if value is None:
            return HTTPTransport._rate_limit_reset_after(response)
        try:
            return max(float(value), 0)
        except ValueError:
            try:
                retry_date = email.utils.parsedate_to_datetime(value)
            except (TypeError, ValueError):
                return HTTPTransport._rate_limit_reset_after(response)
            if retry_date is None:
                return HTTPTransport._rate_limit_reset_after(response)
            return max(retry_date.timestamp() - time.time(), 0)

    @staticmethod
    def _rate_limit_reset_after(response: httpx.Response) -> float | None:
        value = response.headers.get("x-ratelimit-reset")
        if value is None:
            return None
        try:
            return max(float(value) - time.time(), 0)
        except ValueError:
            return None

    def get(self, path: str, *, params: Params = None) -> dict[str, Any]:
        return self._json(self._request("GET", path, params=params))

    def post(self, path: str, *, body: JSONBody = None) -> dict[str, Any]:
        return self._json(self._request("POST", path, json=body))

    def put(self, path: str, *, body: JSONBody = None) -> dict[str, Any]:
        return self._json(self._request("PUT", path, json=body))

    def get_bytes(self, path: str, *, params: Params = None) -> bytes:
        return self._bytes(
            self._request("GET", path, params=params, timeout=self._file_timeout)
        )

    def post_multipart(
        self, path: str, *, files: dict[str, Any], data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self._json(
            self._request("POST", path, files=files, data=data, timeout=self._file_timeout)
        )

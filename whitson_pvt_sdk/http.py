import logging
import threading
import time
from types import TracebackType
from typing import Any, TypeAlias, cast

import httpx

from whitson_pvt_sdk._retry import rate_limit_reset_after, response_retry_after, retry_delay
from whitson_pvt_sdk.errors import (
    APIError,
    AuthError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from whitson_pvt_sdk.shared.models import ClientCredentials, RetryConfig, TokenData

logger = logging.getLogger("whitson_pvt_sdk")

JSONBody: TypeAlias = dict[str, Any] | list[dict[str, Any]] | None

Params: TypeAlias = dict[str, str | int] | None

_MIN_TOKEN_LIFETIME = 300


class _BearerAuth(httpx.Auth):
    def __init__(self, transport: "HTTPTransport") -> None:
        self._transport = transport

    def auth_flow(self, request: httpx.Request) -> Any:
        request.headers["Authorization"] = f"Bearer {self._transport.get_access_token()}"
        yield request


class HTTPTransport:
    def __init__(
        self,
        credentials: ClientCredentials,
        base_url: str,
        *,
        version: str = "v1",
        retry_config: RetryConfig | None = None,
        timeout: float = 30.0,
        file_timeout: float = 60.0,
    ) -> None:
        self._token_url = f"{base_url.rstrip('/')}/external/{version}/auth/token"
        self._credentials = credentials
        self._retry_config = retry_config or RetryConfig()
        self._file_timeout = file_timeout

        self._cached_access_token: str | None = None
        self._cached_expires_at: float = 0.0
        self._token_lock = threading.Lock()

        self._http = httpx.Client(
            auth=_BearerAuth(self),
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

    # ── token management ──

    def get_access_token(self) -> str:
        token = self._valid_cached_token()
        if token is not None:
            return token

        with self._token_lock:
            token = self._valid_cached_token()
            if token is not None:
                return token
            return self._exchange_token()

    def _valid_cached_token(self) -> str | None:
        if (
            self._cached_access_token
            and self._cached_expires_at > time.time() + _MIN_TOKEN_LIFETIME
        ):
            return self._cached_access_token
        return None

    def _exchange_token(self) -> str:
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
                if self._should_retry_token_response(response, attempt):
                    self._sleep_before_token_retry(attempt, response)
                    response.close()
                    continue
                response.raise_for_status()
                token_data = TokenData.model_validate(response.json())
                self._cached_access_token = token_data.access_token
                self._cached_expires_at = time.time() + token_data.expires_in
                logger.debug("Access token cached: expires_in=%s", token_data.expires_in)
                return self._cached_access_token
            except httpx.TimeoutException as e:
                if self._has_token_attempt_remaining(attempt):
                    self._sleep_before_token_retry(attempt)
                    continue
                logger.warning("Authentication request timed out")
                raise AuthError("Authentication service timeout") from e
            except httpx.HTTPStatusError as e:
                self._raise_token_status_error(e)
            except httpx.HTTPError as e:
                if self._has_token_attempt_remaining(attempt):
                    self._sleep_before_token_retry(attempt)
                    continue
                logger.warning("Authentication request failed: error=%s", e)
                raise AuthError("Authentication service unavailable") from e

        raise RuntimeError("Authentication retry loop exhausted without returning or raising")

    def _should_retry_token_response(self, response: httpx.Response, attempt: int) -> bool:
        return (
            self._has_token_attempt_remaining(attempt)
            and response.status_code in self._retry_config.statuses
        )

    def _has_token_attempt_remaining(self, attempt: int) -> bool:
        return attempt < self._retry_config.max_attempts

    def _sleep_before_token_retry(
        self, attempt: int, response: httpx.Response | None = None
    ) -> None:
        delay = retry_delay(response, self._retry_config, attempt)
        logger.debug(
            "Retrying authentication request: attempt=%s status=%s delay=%.3f",
            attempt,
            response.status_code if response is not None else None,
            delay,
        )
        time.sleep(delay)

    def _raise_token_status_error(self, error: httpx.HTTPStatusError) -> None:
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

    # ── response helpers ──

    @staticmethod
    def _response_body(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return response.text

    @classmethod
    def _error_message(cls, response: httpx.Response) -> str:
        body = cls._response_body(response)
        if isinstance(body, dict):
            validation_message = cls._validation_errors_message(body.get("errors"))
            if validation_message is not None:
                return validation_message

            message = body.get("message")
            if isinstance(message, str) and message:
                return message
        if isinstance(body, str) and body:
            return body
        return f"HTTP {response.status_code}"

    @staticmethod
    def _validation_errors_message(errors: object) -> str | None:
        if not isinstance(errors, list) or not errors:
            return None

        for error in errors:
            if not isinstance(error, dict):
                return None
            error_details = cast(dict[str, Any], error)

            message = error_details.get("message")
            if not isinstance(message, str) or not message:
                return None

        return f"Validation Error: {errors}"

    @classmethod
    def _raise_for_status(cls, response: httpx.Response) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return
        body = cls._response_body(response)
        msg = cls._error_message(response)
        request_id = response.headers.get("x-request-id")
        logger.warning(
            "API request failed: status=%s request_id=%s message=%s",
            status,
            request_id,
            msg,
        )
        if status in (401, 403):
            raise AuthError(msg, status_code=status, response_body=body, request_id=request_id)
        if status == 404:
            raise NotFoundError(msg, status_code=status, response_body=body, request_id=request_id)
        if status in (400, 422):
            raise ValidationError(
                msg, status_code=status, response_body=body, request_id=request_id
            )
        if status == 429:
            raise RateLimitError(
                msg,
                status_code=status,
                response_body=body,
                request_id=request_id,
                retry_after_seconds=response_retry_after(response),
            )
        raise APIError(msg, status_code=status, response_body=body, request_id=request_id)

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
                logger.debug(
                    "Sending API request: method=%s path=%s attempt=%s",
                    method,
                    path,
                    attempt,
                )
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
                    self._sleep_before_retry(attempt, method=method, path=path, cause=exc)
                    continue
                logger.warning(
                    "API request failed before response: method=%s path=%s error=%s",
                    method,
                    path,
                    exc,
                )
                raise APIError(f"Request failed: {exc}") from exc

            if self._should_retry_response(method, response, attempt):
                self._sleep_before_retry(attempt, response, method=method, path=path)
                response.close()
                continue

            return response

        raise RuntimeError("Retry loop exhausted without returning or raising")

    def _should_retry_exception(self, method: str, attempt: int) -> bool:
        return self._is_retryable_method(method) and self._has_attempt_remaining(attempt)

    def _should_retry_response(self, method: str, response: httpx.Response, attempt: int) -> bool:
        if not self._has_attempt_remaining(attempt):
            return False
        if response.status_code not in self._retry_config.statuses:
            return False
        return response.status_code == 429 or self._is_retryable_method(method)

    def _is_retryable_method(self, method: str) -> bool:
        return method in self._retry_config.methods

    def _has_attempt_remaining(self, attempt: int) -> bool:
        return attempt < self._retry_config.max_attempts

    def _sleep_before_retry(
        self,
        attempt: int,
        response: httpx.Response | None = None,
        *,
        method: str | None = None,
        path: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        retry_after = retry_delay(response, self._retry_config, attempt)
        logger.debug(
            "Retrying API request: method=%s path=%s attempt=%s status=%s delay=%.3f cause=%s",
            method,
            path,
            attempt,
            response.status_code if response is not None else None,
            retry_after,
            cause,
        )
        time.sleep(retry_after)

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        return response_retry_after(response)

    @staticmethod
    def _rate_limit_reset_after(response: httpx.Response) -> float | None:
        return rate_limit_reset_after(response)

    def get(self, path: str, *, params: Params = None) -> dict[str, Any]:
        return self._json(self._request("GET", path, params=params))

    def post(self, path: str, *, body: JSONBody = None) -> dict[str, Any]:
        return self._json(self._request("POST", path, json=body))

    def put(self, path: str, *, body: JSONBody = None) -> dict[str, Any]:
        return self._json(self._request("PUT", path, json=body))

    def get_bytes(self, path: str, *, params: Params = None) -> bytes:
        return self._bytes(self._request("GET", path, params=params, timeout=self._file_timeout))

    def post_multipart(
        self, path: str, *, files: dict[str, Any], data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self._json(
            self._request("POST", path, files=files, data=data, timeout=self._file_timeout)
        )

import logging
import time
from typing import Any, TypeAlias

import httpx

from whitson_pvt_sdk._retry import retry_after, retry_delay
from whitson_pvt_sdk.auth import CredentialAuth
from whitson_pvt_sdk.credentials import Credential
from whitson_pvt_sdk.errors import (
    APIError,
    AuthError,
    NoResponseError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from whitson_pvt_sdk.shared.models import HTTPMethod, RetryConfig

logger = logging.getLogger("whitson_pvt_sdk")

JSONBody: TypeAlias = dict[str, Any] | list[dict[str, Any]] | None

Params: TypeAlias = dict[str, str | int | float | bool] | None


class HTTPTransport:
    def __init__(
        self,
        credential: Credential,
        base_url: str,
        *,
        retry_config: RetryConfig = RetryConfig(),
        timeout: float = 30.0,
        file_timeout: float = 60.0,
    ) -> None:
        self._retry_config = retry_config
        self._file_timeout = file_timeout
        self._http = httpx.Client(
            auth=CredentialAuth(credential),
            base_url=f"{base_url.rstrip('/')}/external/v2",
            timeout=timeout,
        )

    def close(self) -> None:
        self._http.close()

    def _request(
        self,
        method: HTTPMethod,
        path: str,
        *,
        timeout: httpx.Timeout | float,
        params: Params = None,
        json: JSONBody = None,
        files: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        attempt = 1
        while True:
            logger.debug("Sending API request: method=%s path=%s attempt=%s", method, path, attempt)
            outcome: httpx.Response | httpx.TransportError
            try:
                outcome = self._http.request(
                    method,
                    path,
                    params=params,
                    json=json,
                    files=files,
                    data=data,
                    timeout=timeout,
                )
            except httpx.TransportError as exc:
                outcome = exc
            delay = retry_delay(self._retry_config, method, attempt, outcome)
            if delay is None:
                break
            logger.debug(
                "Retrying API request: method=%s path=%s attempt=%s outcome=%s delay=%.3f",
                method,
                path,
                attempt,
                outcome.status_code if isinstance(outcome, httpx.Response) else outcome,
                delay,
            )
            if isinstance(outcome, httpx.Response):
                outcome.close()
            time.sleep(delay)
            attempt += 1

        match outcome:
            case httpx.Response():
                _raise_for_status(outcome)
                return outcome
            case httpx.TransportError():
                logger.warning(
                    "API request failed before response: method=%s path=%s error=%s",
                    method,
                    path,
                    outcome,
                )
                raise NoResponseError(f"Request failed: {outcome}") from outcome

    def get(self, path: str, *, params: Params = None) -> dict[str, Any]:
        return self._request("GET", path, params=params, timeout=self._http.timeout).json()

    def post(self, path: str, *, body: JSONBody = None) -> dict[str, Any]:
        return self._request("POST", path, json=body, timeout=self._http.timeout).json()

    def put(self, path: str, *, body: JSONBody = None) -> dict[str, Any]:
        return self._request("PUT", path, json=body, timeout=self._http.timeout).json()

    def patch(self, path: str, *, body: JSONBody = None) -> dict[str, Any]:
        return self._request("PATCH", path, json=body, timeout=self._http.timeout).json()

    def delete(self, path: str) -> None:
        self._request("DELETE", path, timeout=self._http.timeout)

    def get_bytes(self, path: str, *, params: Params = None) -> bytes:
        return self._request("GET", path, params=params, timeout=self._file_timeout).content

    def post_multipart(
        self, path: str, *, files: dict[str, Any], data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self._request(
            "POST", path, files=files, data=data, timeout=self._file_timeout
        ).json()


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_success:
        return
    status = response.status_code
    try:
        body: object = response.json()
    except ValueError:
        body = response.text
    message = _error_message(status, body)
    request_id = response.headers.get("x-request-id")
    logger.warning(
        "API request failed: status=%s request_id=%s message=%s", status, request_id, message
    )
    match status:
        case 401 | 403:
            raise AuthError(message, status, response_body=body, request_id=request_id)
        case 404:
            raise NotFoundError(message, status, response_body=body, request_id=request_id)
        case 400 | 422:
            raise ValidationError(message, status, response_body=body, request_id=request_id)
        case 429:
            raise RateLimitError(
                message,
                status,
                response_body=body,
                request_id=request_id,
                retry_after_seconds=retry_after(response),
            )
        case _:
            raise APIError(message, status, response_body=body, request_id=request_id)


def _error_message(status: int, body: object) -> str:
    match body:
        case {"errors": [_, *_] as errors} if all(
            isinstance(error, dict) and isinstance(error.get("message"), str) and error["message"]
            for error in errors
        ):
            return f"Validation Error: {errors}"
        case {"message": str(message)} if message:
            return message
        case str() if body:
            return body
        case _:
            return f"HTTP {status}"

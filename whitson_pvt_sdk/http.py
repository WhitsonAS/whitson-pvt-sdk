import logging
import re
import time
from collections.abc import Mapping
from typing import Any, TypeAlias

import httpx2

from whitson_pvt_sdk._retry import retry_after, retry_delay
from whitson_pvt_sdk.auth import CredentialAuth
from whitson_pvt_sdk.credentials import Credential
from whitson_pvt_sdk.errors import (
    APIError,
    AuthError,
    ConfigurationError,
    NoResponseError,
    NotFoundError,
    RateLimitError,
    RequestRefusedError,
    ResponseError,
    ValidationError,
)
from whitson_pvt_sdk.shared.models import ApiResponse, HTTPMethod, RetryConfig

logger = logging.getLogger("whitson_pvt_sdk")

JSONBody: TypeAlias = dict[str, Any] | list[dict[str, Any]] | None

Params: TypeAlias = Mapping[str, str | int | float | bool] | None

API_PREFIX = "/external/v2"
_SEGMENT = re.compile(r"[A-Za-z0-9._~-]+")


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
        self._http = httpx2.Client(
            auth=CredentialAuth(credential),
            base_url=f"{base_url.rstrip('/')}{API_PREFIX}",
            timeout=timeout,
        )

    def close(self) -> None:
        self._http.close()

    def _request(
        self,
        method: HTTPMethod,
        path: str,
        *,
        timeout: httpx2.Timeout | float,
        params: Params = None,
        json: JSONBody = None,
        files: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> httpx2.Response:
        attempt = 1
        while True:
            logger.debug("Sending API request: method=%s path=%s attempt=%s", method, path, attempt)
            outcome: httpx2.Response | httpx2.TransportError
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
            except httpx2.TransportError as exc:
                outcome = exc
            delay = retry_delay(self._retry_config, method, attempt, outcome)
            if delay is None:
                break
            logger.debug(
                "Retrying API request: method=%s path=%s attempt=%s outcome=%s delay=%.3f",
                method,
                path,
                attempt,
                outcome.status_code if isinstance(outcome, httpx2.Response) else outcome,
                delay,
            )
            if isinstance(outcome, httpx2.Response):
                outcome.close()
            time.sleep(delay)
            attempt += 1

        match outcome:
            case httpx2.Response():
                raise_for_status(outcome)
                return outcome
            case httpx2.TransportError():
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

    def request(
        self, method: HTTPMethod, path: str, *, params: Params = None, body: JSONBody = None
    ) -> ApiResponse:
        response = self._request(
            method, external_path(path), params=params, json=body, timeout=self._file_timeout
        )
        return ApiResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            content=response.content,
        )

    def post_multipart(
        self, path: str, *, files: dict[str, Any], data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self._request(
            "POST", path, files=files, data=data, timeout=self._file_timeout
        ).json()


def route_segments(path: str) -> list[str]:
    segments = path.removeprefix("/").split("/")
    if segments[:2] == API_PREFIX.lstrip("/").split("/"):
        return segments[2:]
    return segments


def external_path(path: str) -> str:
    segments = route_segments(path)
    if not segments or any(
        segment in (".", "..") or not _SEGMENT.fullmatch(segment) for segment in segments
    ):
        raise ConfigurationError(
            f"Refusing the path {path!r}: give a route under {API_PREFIX}, such as /regions or "
            f"{API_PREFIX}/samples/123, without a host, '..', percent-encoding or a query string."
        )
    return "/" + "/".join(segments)


def raise_for_status(response: httpx2.Response) -> None:
    if response.is_success:
        return
    status = response.status_code
    try:
        body: object = response.json()
    except ValueError:
        body = response.text
    server_message = _server_message(body)
    message = _error_message(status, body, server_message)
    request_id = response.headers.get("x-request-id")
    logger.warning(
        "API request failed: status=%s request_id=%s message=%s", status, request_id, message
    )
    if status == 429:
        raise RateLimitError(
            message,
            status,
            response_body=body,
            request_id=request_id,
            server_message=server_message,
            retry_after_seconds=retry_after(response),
        )
    raise _error_type(response)(
        message, status, response_body=body, request_id=request_id, server_message=server_message
    )


def _error_type(response: httpx2.Response) -> type[ResponseError]:
    match response.status_code:
        case 401 | 403:
            return AuthError
        case 404:
            return NotFoundError
        case 400 | 422:
            return ValidationError
        case status if response.is_client_error and status != 408:
            return RequestRefusedError
        case _:
            return APIError


def _server_message(body: object) -> str | None:
    match body:
        case {"message": str(message)} if message:
            return message
        case _:
            return None


def _error_message(status: int, body: object, server_message: str | None) -> str:
    match body:
        case {"errors": [_, *_] as errors} if all(
            isinstance(error, dict) and isinstance(error.get("message"), str) and error["message"]
            for error in errors
        ):
            return f"Validation Error: {errors}"
        case _ if server_message is not None:
            return server_message
        case str() if body:
            return body
        case _:
            return f"HTTP {status}"

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any

import httpx

from .._models.auth import ClientCredentials
from ..auth import TokenManager
from ..errors import APIError, AuthError, NotFoundError, ValidationError

logger = logging.getLogger(__name__)


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
    ) -> None:
        token_kwargs: dict[str, str] = {}
        if auth0_domain:
            token_kwargs["auth0_domain"] = auth0_domain
        if audience:
            token_kwargs["audience"] = audience

        self._http = httpx.Client(
            auth=_BearerAuth(TokenManager(credentials, **token_kwargs)),
            base_url=f"{base_url.rstrip('/')}/external/{version}",
            timeout=30.0,
        )

    def __enter__(self) -> HTTPTransport:
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

    # -- helpers -----------------------------------------------------------

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

    # -- verbs -------------------------------------------------------------

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._json(self._http.get(path, params=params))

    def post(self, path: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._json(self._http.post(path, json=body))

    def put(self, path: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._json(self._http.put(path, json=body))

    def get_bytes(self, path: str, *, params: dict[str, Any] | None = None) -> bytes:
        return self._bytes(self._http.get(path, params=params, timeout=60.0))

    def post_multipart(
        self, path: str, *, files: dict[str, Any], data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self._json(self._http.post(path, files=files, data=data, timeout=60.0))

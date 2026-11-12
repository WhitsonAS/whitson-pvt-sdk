import asyncio
from collections.abc import AsyncGenerator

import anyio.to_thread
import httpx2
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server import create_proxy
from fastmcp.server.providers.proxy import ProxyClient

from whitson_pvt_sdk import __version__
from whitson_pvt_sdk.auth import BearerSource, resolve_base_url, resolve_credential, set_bearer
from whitson_pvt_sdk.errors import AuthError, NoResponseError, ResponseError, SDKError

CLIENT_HEADER = "X-PVT-Client"


class LoginBearer(httpx2.Auth):
    requires_request_body = True

    def __init__(self, bearer: BearerSource, base_url: str) -> None:
        self._bearer = bearer
        self._base_url = base_url

    async def async_auth_flow(
        self, request: httpx2.Request
    ) -> AsyncGenerator[httpx2.Request, httpx2.Response]:
        token = await anyio.to_thread.run_sync(self._bearer.current, str(request.url))
        set_bearer(request.headers, token)
        response = yield request
        if response.status_code == 401:
            renewed = await anyio.to_thread.run_sync(self._bearer.renewed_after_rejection)
            if renewed is None:
                raise AuthError(
                    f"{self._base_url}/mcp refused the API token: personal tokens are not "
                    f"available on MCP yet. Unset WHITSON_PVT_TOKEN and run `wpvt auth login "
                    f"--url {self._base_url}`.",
                    401,
                )
            set_bearer(request.headers, renewed)
            response = yield request
            if response.status_code == 401:
                raise AuthError(
                    f"{self._base_url}/mcp refused the stored login. Run `wpvt auth login --url "
                    f"{self._base_url}`.",
                    401,
                )
        if response.status_code == 403:
            raise AuthError(
                f"{self._base_url}/mcp refused access with this credential (HTTP 403).", 403
            )


def serve(url: str | None, *, verbose: bool) -> None:
    base_url = resolve_base_url(url)
    credential = resolve_credential(base_url, token=None).credential
    transport = StreamableHttpTransport(
        f"{base_url}/mcp",
        headers={CLIENT_HEADER: f"wpvt/{__version__}"},
        auth=LoginBearer(BearerSource(credential), base_url),
    )
    asyncio.run(_serve(transport, base_url, "DEBUG" if verbose else "WARNING"))


async def _serve(transport: StreamableHttpTransport, base_url: str, log_level: str) -> None:
    backend = ProxyClient(transport, forward_incoming_headers=False)
    try:
        async with backend.new() as client:
            await client.list_tools()
    except Exception as exc:
        raise _startup_error(exc, base_url) from None
    proxy = create_proxy(backend, name="wpvt", version=__version__, provider_error_strategy="raise")
    await proxy.run_stdio_async(show_banner=False, log_level=log_level)


def _startup_error(error: BaseException, base_url: str) -> SDKError:
    for cause in _causes(error):
        match cause:
            case SDKError():
                return cause
            case httpx2.HTTPStatusError(response=response):
                return ResponseError(
                    f"{base_url}/mcp answered HTTP {response.status_code}.", response.status_code
                )
            case httpx2.TransportError():
                return NoResponseError(f"Could not reach {base_url}/mcp: {cause}")
            case _:
                pass
    return NoResponseError(f"Could not start the MCP proxy for {base_url}/mcp: {error}")


def _causes(error: BaseException) -> list[BaseException]:
    found: list[BaseException] = []
    pending = [error]
    while pending:
        current = pending.pop(0)
        if current in found:
            continue
        found.append(current)
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)
        pending.extend(
            cause for cause in (current.__cause__, current.__context__) if cause is not None
        )
    return found

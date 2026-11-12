import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
import uvicorn
from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from fastmcp.server.dependencies import get_access_token, get_http_headers
from mcp.types import CallToolResult, JSONRPCError, JSONRPCMessage, JSONRPCResponse, ListToolsResult
from pydantic import TypeAdapter
from starlette.requests import Request
from starlette.responses import JSONResponse
from typer.testing import CliRunner

from tests.conftest import make_login
from whitson_pvt_sdk import __version__
from whitson_pvt_sdk._store import ActiveLogin, CredentialStore, InvalidLogin
from whitson_pvt_sdk.cli._app import app
from whitson_pvt_sdk.credentials import StoredLogin

runner = CliRunner()
_message: TypeAdapter[JSONRPCMessage] = TypeAdapter(JSONRPCMessage)


class Backend:
    def __init__(self) -> None:
        self.accepted = {"fresh-access": "ada"}
        self.renewal: dict[str, str] | None = {
            "access_token": "fresh-access",
            "refresh_token": "refresh-2",
        }
        self.paths: list[str] = []
        self.refreshed_with: list[str] = []
        self.url = ""


def _backend_app(backend: Backend):
    class Verifier(StaticTokenVerifier):
        async def verify_token(self, token: str):
            self.tokens = {
                accepted: {"client_id": name, "scopes": []}
                for accepted, name in backend.accepted.items()
            }
            return await super().verify_token(token)

    server = FastMCP("backend", auth=Verifier(tokens={}))

    @server.tool
    def whoami() -> dict[str, str | None]:
        token = get_access_token()
        return {
            "client_id": None if token is None else token.client_id,
            "client_header": get_http_headers().get("x-pvt-client"),
        }

    @server.custom_route("/oauth/token", methods=["POST"])
    async def token(request: Request) -> JSONResponse:
        form = await request.form()
        backend.refreshed_with.append(str(form["refresh_token"]))
        if backend.renewal is None:
            return JSONResponse({"error": "invalid_grant"}, status_code=403)
        return JSONResponse({**backend.renewal, "token_type": "Bearer", "expires_in": 3600})

    inner = server.http_app(path="/mcp")

    async def recording(scope, receive, send):
        if scope["type"] == "http":
            backend.paths.append(scope["path"])
        await inner(scope, receive, send)

    return recording


@pytest.fixture
def backend() -> Iterator[Backend]:
    state = Backend()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    state.url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(_backend_app(state), log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "backend did not start"
        time.sleep(0.02)
    yield state
    server.should_exit = True
    thread.join(timeout=10)


def _save_login(store: CredentialStore, url: str, *, expired: bool) -> None:
    login = make_login(
        url,
        access="old-access",
        refresh="refresh-1",
        expires_in=timedelta(hours=-1 if expired else 1),
    )
    login = StoredLogin.model_validate(
        {**login.model_dump(), "token_endpoint": f"{url}/oauth/token", "audience": f"{url}/mcp"}
    )
    with store.transaction() as transaction:
        transaction.put(login)
        transaction.set_default(login.base_url)


class Proxy:
    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self.stdout_lines: list[str] = []
        self._lines: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self._next_id = 0

    def _read(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def request(
        self, method: str, params: dict[str, object] | None = None
    ) -> JSONRPCResponse | JSONRPCError:
        self._next_id += 1
        self.send({"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params or {}})
        while True:
            line = self._lines.get(timeout=30)
            assert line is not None, "the proxy closed stdout"
            self.stdout_lines.append(line)
            match _message.validate_json(line):
                case JSONRPCResponse() | JSONRPCError() as reply if reply.id == self._next_id:
                    return reply
                case _:
                    pass

    def result(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        match self.request(method, params):
            case JSONRPCResponse(result=result):
                return result
            case JSONRPCError(error=error):
                pytest.fail(f"{method} failed: {error}")

    def send(self, message: dict[str, object]) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def close(self) -> str:
        assert self.process.stdin is not None
        self.process.stdin.close()
        self.process.wait(timeout=30)
        while (line := self._lines.get(timeout=30)) is not None:
            self.stdout_lines.append(line)
        assert self.process.stderr is not None
        return self.process.stderr.read()


def _start_proxy(tmp_path: Path, url: str) -> Proxy:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in ("WHITSON_PVT_TOKEN", "WHITSON_PVT_URL")
    }
    environment.update(
        XDG_CONFIG_HOME=str(tmp_path / "config"),
        PYTHON_KEYRING_BACKEND="keyring.backends.fail.Keyring",
    )
    process = subprocess.Popen(
        [sys.executable, "-c", "from whitson_pvt_sdk.cli import main; main()", "mcp", "--url", url],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    return Proxy(process)


def test_mcp_proxies_the_remote_tools_with_the_stored_login(backend, store, tmp_path):
    _save_login(store, backend.url, expired=True)
    proxy = _start_proxy(tmp_path, backend.url)

    proxy.result(
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    )
    proxy.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    tools = ListToolsResult.model_validate(proxy.result("tools/list"))
    called = CallToolResult.model_validate(
        proxy.result("tools/call", {"name": "whoami", "arguments": {}})
    )

    backend.accepted = {}
    backend.renewal = None
    refused = proxy.request("tools/call", {"name": "whoami", "arguments": {}})
    stderr = proxy.close()

    assert [tool.name for tool in tools.tools] == ["whoami"]
    assert called.structured_content == {
        "client_id": "ada",
        "client_header": f"wpvt/{__version__}",
    }
    assert backend.refreshed_with[0] == "refresh-1"
    match store.get(backend.url):
        case InvalidLogin(login=login):
            assert login.refresh_token.get_secret_value() == "refresh-2"
        case other:
            pytest.fail(f"the login should be marked invalid after the refused renewal: {other}")
    match refused:
        case JSONRPCResponse(result=result):
            refusal = CallToolResult.model_validate(result)
            assert refusal.is_error
            assert f"wpvt auth login --url {backend.url}" in refusal.model_dump_json()
        case JSONRPCError(error=error):
            assert f"wpvt auth login --url {backend.url}" in error.message
    for line in proxy.stdout_lines:
        _message.validate_json(line)
    for secret in ("old-access", "fresh-access", "refresh-1", "refresh-2"):
        assert secret not in stderr
        assert secret not in "".join(proxy.stdout_lines)


def test_mcp_renews_an_expiring_login_before_serving_and_keeps_the_rotated_tokens(backend, store):
    _save_login(store, backend.url, expired=True)
    backend.accepted = {}

    result = runner.invoke(app, ["mcp", "--url", backend.url])

    assert result.exit_code == 3
    assert backend.refreshed_with == ["refresh-1", "refresh-2"]
    match store.get(backend.url):
        case ActiveLogin(login=login):
            assert login.access_token.get_secret_value() == "fresh-access"
            assert login.refresh_token.get_secret_value() == "refresh-2"
        case other:
            pytest.fail(f"expected the rotated login, found {other}")
    assert f"refused the stored login. Run `wpvt auth login --url {backend.url}`" in result.stderr


def test_mcp_with_an_api_token_says_personal_tokens_are_not_available(backend, monkeypatch):
    monkeypatch.setenv("WHITSON_PVT_TOKEN", "whitson_pvt_secret")

    result = runner.invoke(app, ["mcp", "--url", backend.url])

    assert result.exit_code == 3
    assert "personal tokens are not available on MCP yet" in result.stderr
    assert f"wpvt auth login --url {backend.url}" in result.stderr
    assert result.stdout == ""
    assert "whitson_pvt_secret" not in result.stderr


def test_mcp_without_a_login_exits_before_serving(backend):
    result = runner.invoke(app, ["mcp", "--url", backend.url])

    assert result.exit_code == 2
    assert f"wpvt auth login --url {backend.url}" in result.stderr
    assert result.stdout == ""
    assert backend.paths == []


def test_mcp_reports_an_unreachable_deployment(store):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    sock.close()
    _save_login(store, url, expired=False)

    result = runner.invoke(app, ["mcp", "--url", url])

    assert result.exit_code == 4
    assert f"Could not reach {url}/mcp" in result.stderr

import base64
import hashlib
import hmac
import secrets
import socketserver
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Literal
from urllib.parse import parse_qs, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from pydantic import ValidationError as PydanticValidationError

from whitson_pvt_sdk._oauth import (
    AuthConfig,
    OAuthError,
    ProviderMetadata,
    TokenGranted,
    TokenRefused,
    TokenResponse,
    TokenResult,
    discover,
    fetch_auth_config,
    oauth_client,
    parse_oauth_error,
    post_form,
    request_token,
    revoke_refresh_token,
)
from whitson_pvt_sdk._store import CredentialStore, RemovedLogin
from whitson_pvt_sdk._trust import (
    Confirmation,
    FirstUse,
    IssuerChanged,
    KnownDeployment,
    Refused,
    TrustedByAllowlist,
    TrustedByOverride,
    familiarity,
    host_trust,
)
from whitson_pvt_sdk.auth import TOKEN_ENV_VAR
from whitson_pvt_sdk.credentials import StoredLogin
from whitson_pvt_sdk.errors import ConfigurationError, LoginError, SDKError

DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


class BrowserLogin(BaseModel):
    model_config = ConfigDict(frozen=True)

    open_browser: Callable[[str], bool] | None = None
    timeout: float = Field(default=300.0, gt=0)


class DeviceLogin(BaseModel):
    model_config = ConfigDict(frozen=True)


LoginMethod = BrowserLogin | DeviceLogin


class LoggedOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str
    revocation: Literal["revoked", "not_offered", "failed", "skipped"]


def login(
    base_url: str,
    method: LoginMethod,
    *,
    output: Callable[[str], None],
    confirm: Callable[[Confirmation], bool] | None = None,
    trust_host: bool = False,
) -> StoredLogin:
    match host_trust(base_url, trust_host=trust_host):
        case TrustedByAllowlist(url=url) | TrustedByOverride(url=url):
            pass
        case Refused(reason=reason):
            raise ConfigurationError(reason)
    with oauth_client() as http:
        config = fetch_auth_config(http, url)
        if isinstance(method, DeviceLogin) and not config.device_login:
            raise ConfigurationError(
                f"Device login is not enabled on {url}. Log in with a browser from a machine "
                f"that has one, or use an API token in {TOKEN_ENV_VAR}."
            )
        match familiarity(url, config.issuer):
            case FirstUse() | IssuerChanged() as confirmation:
                if confirm is None:
                    raise ConfigurationError(
                        f"{confirmation.describe()} Pass confirm= to login() to ask the user."
                    )
                if not confirm(confirmation):
                    raise LoginError(f"The login to {url} was cancelled; nothing was stored.")
            case KnownDeployment():
                pass
        provider = discover(http, config.issuer)
        match method:
            case BrowserLogin(open_browser=open_browser, timeout=timeout):
                token = _browser_flow(http, config, provider, open_browser, output, timeout)
            case DeviceLogin():
                token = _device_flow(http, config, provider, output)
    if token.refresh_token is None:
        raise LoginError(
            f"{config.issuer} returned no refresh token; the login cannot be kept. "
            "Ask the deployment's administrator to allow offline access for the CLI."
        )
    stored = StoredLogin(
        base_url=url,
        issuer=config.issuer,
        client_id=config.client_id,
        audience=config.audience,
        scopes=config.scopes,
        token_endpoint=provider.token_endpoint,
        access_token=token.access_token,
        refresh_token=token.refresh_token,
        expires_at=token.expires_at(),
    )
    with CredentialStore.from_environment().transaction() as transaction:
        transaction.put(stored)
        transaction.set_default(stored.base_url)
    return stored


def logout(base_url: str) -> LoggedOut | None:
    with CredentialStore.from_environment().transaction() as transaction:
        removed = transaction.remove(base_url)
    return None if removed is None else _revoke(removed)


def logout_all() -> list[LoggedOut]:
    with CredentialStore.from_environment().transaction() as transaction:
        removed = [transaction.remove(url) for url in transaction.urls()]
    return [_revoke(entry) for entry in removed if entry is not None]


def _without_a_browser(config: AuthConfig) -> str:
    if config.device_login:
        return (
            "Without a browser on this machine, log in with a code instead "
            "(wpvt auth login --device)."
        )
    return f"Without a browser on this machine, use an API token in {TOKEN_ENV_VAR} instead."


def _scope(config: AuthConfig) -> str:
    return " ".join([*config.scopes, "offline_access"])


class _CodeReceived(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: SecretStr


class _AuthorizationRefused(BaseModel):
    model_config = ConfigDict(frozen=True)

    error: OAuthError


class _StateMismatch(BaseModel):
    model_config = ConfigDict(frozen=True)


class _CallbackTimedOut(BaseModel):
    model_config = ConfigDict(frozen=True)


_Callback = _CodeReceived | _AuthorizationRefused | _StateMismatch


def _browser_flow(
    http: httpx.Client,
    config: AuthConfig,
    provider: ProviderMetadata,
    open_browser: Callable[[str], bool] | None,
    output: Callable[[str], None],
    timeout: float,
) -> TokenResponse:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    state = secrets.token_urlsafe(32)
    with _CallbackServer(state) as server:
        redirect_uri = f"http://127.0.0.1:{server.server_address[1]}/callback"
        params = {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": redirect_uri,
            "scope": _scope(config),
            "audience": config.audience,
            "state": state,
            "code_challenge": challenge.decode().rstrip("="),
            "code_challenge_method": "S256",
        }
        if config.connection is not None:
            params["connection"] = config.connection
        authorize_url = str(httpx.URL(provider.authorization_endpoint).copy_merge_params(params))
        if open_browser is not None and open_browser(authorize_url):
            output(f"Opened a browser to log in. If it did not open, visit:\n{authorize_url}")
        else:
            output(
                f"Open this URL in a browser on this machine to log in:\n{authorize_url}\n"
                + _without_a_browser(config)
            )
        callback = server.wait(timeout)
    match callback:
        case _CodeReceived(code=code):
            result = request_token(
                http,
                provider.token_endpoint,
                {
                    "grant_type": "authorization_code",
                    "client_id": config.client_id,
                    "code": code.get_secret_value(),
                    "code_verifier": verifier,
                    "redirect_uri": redirect_uri,
                },
            )
            match result:
                case TokenGranted(token=token):
                    return token
                case TokenRefused(error=error):
                    raise LoginError(f"The login was refused: {error.describe()}.")
        case _AuthorizationRefused(error=error):
            raise LoginError(f"The login was refused: {error.describe()}.")
        case _StateMismatch():
            raise LoginError(
                "The login callback did not carry this login's state value, so it was "
                "rejected. Run the login again."
            )
        case _CallbackTimedOut():
            raise LoginError(f"Timed out after {timeout:.0f} s waiting for the browser login.")


class _CallbackServer(HTTPServer):
    def __init__(self, state: str) -> None:
        self.expected_state = state
        self.callback: _Callback | None = None
        super().__init__(("127.0.0.1", 0), _CallbackHandler)

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        self.server_name = "127.0.0.1"
        self.server_port = self.server_address[1]

    def wait(self, timeout: float) -> _Callback | _CallbackTimedOut:
        deadline = time.monotonic() + timeout
        while self.callback is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return _CallbackTimedOut()
            self.timeout = remaining
            self.handle_request()
        return self.callback


class _CallbackHandler(BaseHTTPRequestHandler):
    server: _CallbackServer
    timeout = 10

    def do_GET(self) -> None:
        target = urlsplit(self.path)
        if target.path != "/callback" or self.server.callback is not None:
            self._page(404, "Not found.")
            return
        callback = _parse_callback(parse_qs(target.query), self.server.expected_state)
        self.server.callback = callback
        match callback:
            case _CodeReceived():
                self._page(200, "Logged in to whitson PVT. You can close this window.")
            case _AuthorizationRefused() | _StateMismatch():
                self._page(400, "The whitson PVT login failed. Return to the terminal.")

    def log_message(self, format: str, *args: object) -> None:
        return

    def _page(self, status: int, message: str) -> None:
        body = (
            "<!doctype html><meta charset=utf-8><title>whitson PVT</title>"
            f"<p style='font-family:sans-serif'>{message}</p>"
        ).encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def _parse_callback(query: dict[str, list[str]], expected_state: str) -> _Callback:
    state = _single(query, "state")
    if state is None or not hmac.compare_digest(state, expected_state):
        return _StateMismatch()
    error = _single(query, "error")
    if error is not None:
        return _AuthorizationRefused(
            error=OAuthError(error=error, error_description=_single(query, "error_description"))
        )
    code = _single(query, "code")
    if not code:
        return _AuthorizationRefused(error=OAuthError(error="invalid_request"))
    return _CodeReceived(code=SecretStr(code))


def _single(query: dict[str, list[str]], name: str) -> str | None:
    values = query.get(name)
    return values[0] if values is not None and len(values) == 1 else None


class _DeviceAuthorization(BaseModel):
    model_config = ConfigDict(frozen=True)

    device_code: SecretStr
    user_code: str
    verification_uri: str
    verification_uri_complete: str | None = None
    expires_in: int = Field(gt=0)
    interval: int = Field(default=5, gt=0)


class _Granted(BaseModel):
    model_config = ConfigDict(frozen=True)

    token: TokenResponse


class _Pending(BaseModel):
    model_config = ConfigDict(frozen=True)


class _SlowDown(BaseModel):
    model_config = ConfigDict(frozen=True)


class _Denied(BaseModel):
    model_config = ConfigDict(frozen=True)


class _Expired(BaseModel):
    model_config = ConfigDict(frozen=True)


class _Failed(BaseModel):
    model_config = ConfigDict(frozen=True)

    error: OAuthError


_DevicePoll = _Granted | _Pending | _SlowDown | _Denied | _Expired | _Failed

_SLOW_DOWN_SECONDS = 5


def _device_flow(
    http: httpx.Client,
    config: AuthConfig,
    provider: ProviderMetadata,
    output: Callable[[str], None],
) -> TokenResponse:
    endpoint = provider.device_authorization_endpoint
    if endpoint is None:
        raise LoginError(f"{config.issuer} does not offer device login; log in with a browser.")
    response = post_form(
        http,
        endpoint,
        {"client_id": config.client_id, "scope": _scope(config), "audience": config.audience},
    )
    if not response.is_success:
        error = parse_oauth_error(response, endpoint)
        raise LoginError(f"Device login could not start: {error.describe()}.")
    try:
        authorization = _DeviceAuthorization.model_validate_json(response.content)
    except PydanticValidationError:
        raise LoginError(f"{endpoint} returned a response this SDK cannot use.") from None
    output(
        f"To log in, open {authorization.verification_uri} and enter the code "
        f"{authorization.user_code}"
        + (
            f"\nor open {authorization.verification_uri_complete}"
            if authorization.verification_uri_complete
            else ""
        )
    )
    deadline = time.monotonic() + authorization.expires_in
    interval = authorization.interval
    form = {
        "grant_type": DEVICE_GRANT,
        "device_code": authorization.device_code.get_secret_value(),
        "client_id": config.client_id,
    }
    while True:
        time.sleep(interval)
        poll = _device_poll(request_token(http, provider.token_endpoint, form))
        match poll:
            case _Granted(token=token):
                return token
            case _Pending() | _SlowDown() if time.monotonic() >= deadline:
                raise _device_expired()
            case _Pending():
                continue
            case _SlowDown():
                interval += _SLOW_DOWN_SECONDS
            case _Denied():
                raise LoginError("The login was denied in the browser.")
            case _Expired():
                raise _device_expired()
            case _Failed(error=error):
                raise LoginError(f"The device login failed: {error.describe()}.")


def _device_poll(result: TokenResult) -> _DevicePoll:
    match result:
        case TokenGranted(token=token):
            return _Granted(token=token)
        case TokenRefused(error=OAuthError(error="authorization_pending")):
            return _Pending()
        case TokenRefused(error=OAuthError(error="slow_down")):
            return _SlowDown()
        case TokenRefused(error=OAuthError(error="access_denied")):
            return _Denied()
        case TokenRefused(error=OAuthError(error="expired_token")):
            return _Expired()
        case TokenRefused(error=error):
            return _Failed(error=error)


def _device_expired() -> LoginError:
    return LoginError("The device code expired before the login was confirmed. Log in again.")


def _revoke(removed: RemovedLogin) -> LoggedOut:
    if removed.entry is None:
        return LoggedOut(url=removed.base_url, revocation="skipped")
    stored = removed.entry.login
    try:
        with oauth_client() as http:
            endpoint = discover(http, stored.issuer).revocation_endpoint
            if endpoint is None:
                return LoggedOut(url=removed.base_url, revocation="not_offered")
            revoked = revoke_refresh_token(http, endpoint, stored)
    except SDKError:
        return LoggedOut(url=removed.base_url, revocation="failed")
    return LoggedOut(url=removed.base_url, revocation="revoked" if revoked else "failed")

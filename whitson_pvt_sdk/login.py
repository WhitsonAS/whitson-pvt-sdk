import base64
import hashlib
import hmac
import secrets
import socket
import socketserver
import sys
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Literal, TypeVar
from urllib.parse import parse_qs, urlsplit

import httpx2
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from whitson_pvt_sdk._login_page import CONTENT_SECURITY_POLICY, Outcome, login_page
from whitson_pvt_sdk._oauth import (
    AuthConfig,
    DeviceAuthorization,
    OAuthError,
    ProviderMetadata,
    TokenGranted,
    TokenRefused,
    TokenResponse,
    discover,
    fetch_auth_config,
    oauth_client,
    post_oauth,
    request_token,
    revoke_refresh_token,
)
from whitson_pvt_sdk._store import CredentialStore, KeyringCleanup, RemovedLogin
from whitson_pvt_sdk._trust import (
    AudienceChanged,
    Confirmation,
    FirstUse,
    IssuerChanged,
    Proceed,
    host_trust,
    login_decision,
)
from whitson_pvt_sdk.auth import TOKEN_ENV_VAR
from whitson_pvt_sdk.credentials import StoredLogin, host_name, same_origin
from whitson_pvt_sdk.errors import ConfigurationError, LoginError, SDKError

__all__ = [
    "CALLBACK_PORTS",
    "READ_SCOPES",
    "AllScopes",
    "AudienceChanged",
    "BrowserLogin",
    "ChosenScopes",
    "Confirmation",
    "DeviceLogin",
    "FirstUse",
    "IssuerChanged",
    "LoggedOut",
    "LoginMethod",
    "ScopeChoice",
    "login",
    "logout",
    "logout_all",
]

DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"

# Each must be registered as http://127.0.0.1:<port>/callback on the Auth0 command-line application.
CALLBACK_PORTS = (52817, 54631, 57493, 61287)

_Verified = TypeVar("_Verified")


class BrowserLogin(BaseModel):
    model_config = ConfigDict(frozen=True)

    open_browser: Callable[[str], bool] | None = None
    timeout: float = Field(default=300.0, gt=0)


class DeviceLogin(BaseModel):
    model_config = ConfigDict(frozen=True)


LoginMethod = BrowserLogin | DeviceLogin

READ_SCOPES = "read"


class AllScopes(BaseModel):
    model_config = ConfigDict(frozen=True)


class ChosenScopes(BaseModel):
    model_config = ConfigDict(frozen=True)

    names: frozenset[str] = Field(min_length=1)


ScopeChoice = AllScopes | ChosenScopes


Revocation = Literal["revoked", "not_offered", "failed", "skipped"]


class LoggedOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str
    revocation: Revocation
    keyring: KeyringCleanup


def login(
    base_url: str,
    method: LoginMethod,
    *,
    output: Callable[[str], None],
    verify: Callable[[StoredLogin], _Verified],
    scopes: ScopeChoice = AllScopes(),
    confirm: Callable[[Confirmation], bool] | None = None,
    trust_host: bool = False,
) -> _Verified:
    trusted = host_trust(base_url, trust_host=trust_host, resolve=_addresses)
    url = trusted.url
    with oauth_client() as http:
        config = fetch_auth_config(http, url)
        decision = login_decision(
            trusted,
            config.issuer,
            config.audience,
            CredentialStore.from_environment().remembered(url),
        )
        if isinstance(method, DeviceLogin) and not config.device_login:
            raise ConfigurationError(
                f"Device login is not enabled on {url}. Log in with a browser from a machine "
                f"that has one, or use an API token in {TOKEN_ENV_VAR}."
            )
        requested = _requested_scopes(scopes, config, url)
        scope = " ".join([*requested, "offline_access"])
        match decision:
            case Proceed():
                pass
            case FirstUse() | IssuerChanged() | AudienceChanged() as confirmation:
                if confirm is None:
                    raise ConfigurationError(
                        f"{confirmation.describe()} Pass confirm= to login() to ask the user."
                    )
                if not confirm(confirmation):
                    raise LoginError(f"The login to {url} was cancelled; nothing was stored.")
        provider = discover(http, config.issuer)
        match method:
            case BrowserLogin():
                token = _browser_flow(http, config, provider, scope, method, output)
            case DeviceLogin():
                token = _device_flow(http, config, provider, scope, output)
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
        scopes=requested,
        token_endpoint=provider.token_endpoint,
        access_token=token.access_token,
        refresh_token=token.refresh_token,
        expires_at=token.expires_at(),
    )
    verified = verify(stored)
    with CredentialStore.from_environment().transaction() as transaction:
        transaction.put(stored)
        transaction.set_default(stored.base_url)
    return verified


def logout(base_url: str) -> LoggedOut | None:
    with CredentialStore.from_environment().transaction() as transaction:
        removed = transaction.remove(base_url)
    return None if removed is None else _revoke(removed)


def logout_all() -> list[LoggedOut]:
    with CredentialStore.from_environment().transaction() as transaction:
        removed = [transaction.remove(url) for url in transaction.urls()]
    return [_revoke(entry) for entry in removed if entry is not None]


def _addresses(host: str) -> list[str]:
    try:
        found = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return []
    return [str(address[0]) for *_, address in found]


def _without_a_browser(config: AuthConfig) -> str:
    if config.device_login:
        return (
            "Without a browser on this machine, log in with a code instead "
            "(wpvt auth login --device)."
        )
    return f"Without a browser on this machine, use an API token in {TOKEN_ENV_VAR} instead."


def _requested_scopes(choice: ScopeChoice, config: AuthConfig, url: str) -> tuple[str, ...]:
    match choice:
        case AllScopes():
            return config.scopes
        case ChosenScopes(names=names):
            offered = (
                f"Choose from {', '.join(config.scopes)}, or {READ_SCOPES} for every *:read scope."
            )
            unknown = sorted(names - {READ_SCOPES, *config.scopes})
            if unknown:
                raise ConfigurationError(
                    f"{url} does not offer the scope {', '.join(unknown)}. {offered}"
                )
            requested = tuple(
                scope
                for scope in config.scopes
                if scope in names or (READ_SCOPES in names and scope.endswith(":read"))
            )
            if not requested:
                raise ConfigurationError(f"{url} offers no *:read scope. {offered}")
            return requested


class _AwaitingStart(BaseModel):
    model_config = ConfigDict(frozen=True)

    authorize_url: str


class _Started(BaseModel):
    model_config = ConfigDict(frozen=True)


class _CodeReceived(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: SecretStr


class _AuthorizationRefused(BaseModel):
    model_config = ConfigDict(frozen=True)

    error: OAuthError


class _StartedTwice(BaseModel):
    model_config = ConfigDict(frozen=True)


class _StateMismatch(BaseModel):
    model_config = ConfigDict(frozen=True)


class _CallbackTimedOut(BaseModel):
    model_config = ConfigDict(frozen=True)


_Callback = _CodeReceived | _AuthorizationRefused
_Listening = _AwaitingStart | _Started
_Finished = _Callback | _StartedTwice


def _browser_flow(
    http: httpx2.Client,
    config: AuthConfig,
    provider: ProviderMetadata,
    scope: str,
    method: BrowserLogin,
    output: Callable[[str], None],
) -> TokenResponse:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    state = secrets.token_urlsafe(32)

    def authorize_url(redirect_uri: str) -> str:
        params = {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "audience": config.audience,
            "state": state,
            "code_challenge": challenge.decode().rstrip("="),
            "code_challenge_method": "S256",
        }
        if config.connection is not None:
            params["connection"] = config.connection
        return str(httpx2.URL(provider.authorization_endpoint).copy_merge_params(params))

    with _callback_server(state, authorize_url) as server:
        if method.open_browser is not None and method.open_browser(server.start_url):
            output(f"Opened a browser to log in. If it did not open, visit:\n{server.start_url}")
        else:
            output(
                f"Open this URL in a browser on this machine to log in:\n{server.start_url}\n"
                + _without_a_browser(config)
            )
        outcome = server.wait(method.timeout)
    match outcome:
        case _CodeReceived(code=code):
            result = request_token(
                http,
                provider.token_endpoint,
                {
                    "grant_type": "authorization_code",
                    "client_id": config.client_id,
                    "code": code.get_secret_value(),
                    "code_verifier": verifier,
                    "redirect_uri": server.redirect_uri,
                },
            )
            match result:
                case TokenGranted(token=token):
                    return token
                case TokenRefused(error=error):
                    raise LoginError(f"The login was refused: {error.describe()}.")
        case _AuthorizationRefused(error=error):
            raise LoginError(f"The login was refused: {error.describe()}.")
        case _StartedTwice():
            raise LoginError(
                "The login link was opened more than once, so another program on this machine "
                "may have used it first; the login was stopped. Log in again."
            )
        case _CallbackTimedOut():
            raise LoginError(
                f"Timed out after {method.timeout:.0f} s waiting for the browser login."
            )


def _callback_server(state: str, authorize_url: Callable[[str], str]) -> "_CallbackServer":
    failure: OSError | None = None
    for port in CALLBACK_PORTS:
        try:
            return _CallbackServer(port, state, authorize_url)
        except OSError as exc:
            failure = exc
    raise LoginError(
        "Could not listen for the browser login on 127.0.0.1 port "
        f"{', '.join(map(str, CALLBACK_PORTS))} ({failure.strerror if failure else 'no port'}). "
        "Stop the program using one of these ports and log in again, or log in with --device "
        "where the deployment allows it."
    )


class _CallbackServer(HTTPServer):
    # SO_REUSEADDR on Windows would let this bind over another program's listener on the port.
    allow_reuse_address = sys.platform != "win32"

    def __init__(self, port: int, state: str, authorize_url: Callable[[str], str]) -> None:
        super().__init__(("127.0.0.1", port), _CallbackHandler)
        origin = f"http://127.0.0.1:{self.server_address[1]}"
        nonce = secrets.token_urlsafe(32)
        self.expected_state = state
        self.expected_nonce = nonce
        self.redirect_uri = f"{origin}/callback"
        self.start_url = f"{origin}/start?n={nonce}"
        self.phase: _Listening | _Finished = _AwaitingStart(
            authorize_url=authorize_url(self.redirect_uri)
        )

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        self.server_name = "127.0.0.1"
        self.server_port = self.server_address[1]

    def wait(self, timeout: float) -> _Finished | _CallbackTimedOut:
        deadline = time.monotonic() + timeout
        while True:
            match self.phase:
                case _AwaitingStart() | _Started():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return _CallbackTimedOut()
                    self.timeout = remaining
                    self.handle_request()
                case _CodeReceived() | _AuthorizationRefused() | _StartedTwice() as finished:
                    return finished


class _CallbackHandler(BaseHTTPRequestHandler):
    server: _CallbackServer
    timeout = 10

    def do_GET(self) -> None:
        target = urlsplit(self.path)
        query = parse_qs(target.query)
        match (target.path, self.server.phase):
            case ("/start", _AwaitingStart(authorize_url=authorize_url)) if self._nonce_matches(
                query
            ):
                self.server.phase = _Started()
                self._redirect(authorize_url)
            case ("/start", _Started()) if self._nonce_matches(query):
                self.server.phase = _StartedTwice()
                self._page("link_used")
            case ("/callback", _Started()):
                self._callback(query)
            case _:
                self._page("not_found")

    def log_message(self, format: str, *args: object) -> None:
        return

    def _nonce_matches(self, query: dict[str, list[str]]) -> bool:
        return _matches(_single(query, "n"), self.server.expected_nonce)

    def _callback(self, query: dict[str, list[str]]) -> None:
        match _parse_callback(query, self.server.expected_state):
            case _StateMismatch():
                self._page("other_login")
            case _CodeReceived() as callback:
                self.server.phase = callback
                self._page("logged_in")
            case _AuthorizationRefused() as callback:
                self.server.phase = callback
                self._page("login_failed")

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()

    def _page(self, outcome: Outcome) -> None:
        page = login_page(outcome)
        self.send_response(page.status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page.body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        self.end_headers()
        self.wfile.write(page.body)


def _parse_callback(query: dict[str, list[str]], expected_state: str) -> _Callback | _StateMismatch:
    if not _matches(_single(query, "state"), expected_state):
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


def _matches(given: str | None, expected: str) -> bool:
    # compare_digest refuses non-ASCII str, which a percent-encoded query can carry.
    return given is not None and hmac.compare_digest(given.encode(), expected.encode())


def _single(query: dict[str, list[str]], name: str) -> str | None:
    values = query.get(name)
    return values[0] if values is not None and len(values) == 1 else None


_SLOW_DOWN_SECONDS = 5


def _device_flow(
    http: httpx2.Client,
    config: AuthConfig,
    provider: ProviderMetadata,
    scope: str,
    output: Callable[[str], None],
) -> TokenResponse:
    endpoint = provider.device_authorization_endpoint
    if endpoint is None:
        raise LoginError(f"{config.issuer} does not offer device login; log in with a browser.")
    authorization = post_oauth(
        http,
        endpoint,
        {"client_id": config.client_id, "scope": scope, "audience": config.audience},
        DeviceAuthorization,
    )
    if isinstance(authorization, OAuthError):
        raise LoginError(f"Device login could not start: {authorization.describe()}.")
    for page in (authorization.verification_uri, authorization.verification_uri_complete):
        if page is not None and not same_origin(page, config.issuer):
            raise LoginError(
                f"{endpoint} asks you to enter the code at {host_name(page)}, not at the "
                f"login server {host_name(config.issuer)}; refusing to log in."
            )
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
        match request_token(http, provider.token_endpoint, form):
            case TokenGranted(token=token):
                return token
            case TokenRefused(error=OAuthError(error="authorization_pending" | "slow_down")) if (
                time.monotonic() >= deadline
            ):
                raise _device_expired()
            case TokenRefused(error=OAuthError(error="authorization_pending")):
                continue
            case TokenRefused(error=OAuthError(error="slow_down")):
                interval += _SLOW_DOWN_SECONDS
            case TokenRefused(error=OAuthError(error="access_denied")):
                raise LoginError("The login was denied in the browser.")
            case TokenRefused(error=OAuthError(error="expired_token")):
                raise _device_expired()
            case TokenRefused(error=error):
                raise LoginError(f"The device login failed: {error.describe()}.")


def _device_expired() -> LoginError:
    return LoginError("The device code expired before the login was confirmed. Log in again.")


def _revoke(removed: RemovedLogin) -> LoggedOut:
    return LoggedOut(url=removed.base_url, revocation=_revocation(removed), keyring=removed.keyring)


def _revocation(removed: RemovedLogin) -> Revocation:
    stored = removed.login
    if stored is None:
        return "skipped"
    try:
        with oauth_client() as http:
            endpoint = discover(http, stored.issuer).revocation_endpoint
            if endpoint is None:
                return "not_offered"
            revoked = revoke_refresh_token(http, endpoint, stored)
    except SDKError:
        return "failed"
    return "revoked" if revoked else "failed"

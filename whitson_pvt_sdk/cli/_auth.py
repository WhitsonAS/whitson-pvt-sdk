import os
import sys
import webbrowser
from typing import Annotated, Literal

import typer
from pydantic import BaseModel

from whitson_pvt_sdk.auth import (
    TOKEN_ENV_VAR,
    FromArgument,
    FromEnvironment,
    FromStore,
    resolve_base_url,
    resolve_credential,
)
from whitson_pvt_sdk.cli._output import emit, note, reporting
from whitson_pvt_sdk.credentials import Credential
from whitson_pvt_sdk.errors import AuthError, ConfigurationError
from whitson_pvt_sdk.http import HTTPTransport
from whitson_pvt_sdk.login import BrowserLogin, DeviceLogin, LoggedOut, login, logout, logout_all
from whitson_pvt_sdk.shared.models import (
    ApiTokenIdentity,
    Identity,
    LegacyClientIdentity,
    UserTokenIdentity,
)
from whitson_pvt_sdk.v2.resources import Me

auth_app = typer.Typer(
    help="Log in to a whitson PVT deployment, check the login and log out.",
    no_args_is_help=True,
)

UrlOption = Annotated[
    str | None,
    typer.Option(
        "--url",
        help="Deployment URL, such as https://example.pvt.whitson.com. "
        "Defaults to WHITSON_PVT_URL, then the default login.",
    ),
]
JsonOption = Annotated[bool, typer.Option("--json", help="Print one JSON document on stdout.")]


class LoginReport(BaseModel):
    url: str
    identity: Identity


class CredentialReport(BaseModel):
    kind: Literal["api_token", "stored_login"]
    source: Literal["argument", "environment", "store"]


class StatusReport(BaseModel):
    url: str
    credential: CredentialReport
    identity: Identity


class LogoutReport(BaseModel):
    removed: list[LoggedOut]


@auth_app.command("login")
def login_command(
    url: UrlOption = None,
    device: Annotated[
        bool,
        typer.Option(
            "--device", help="Log in with a code on another device, for machines without a browser."
        ),
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Log in through the browser (or --device) and make this login the default."""
    with reporting(json_output=json_output):
        target = resolve_base_url(url)
        if device:
            method: BrowserLogin | DeviceLogin = DeviceLogin()
        elif sys.stdin.isatty() and sys.stderr.isatty():
            method = BrowserLogin(open_browser=webbrowser.open)
        else:
            note(
                "No terminal is attached, so no browser is opened. Without a browser, use --device."
            )
            method = BrowserLogin()
        stored = login(target, method, output=note)
        identity = _identity(stored, stored.base_url)
        if os.environ.get(TOKEN_ENV_VAR):
            note(
                f"{TOKEN_ENV_VAR} is set and takes precedence over this login; unset it to use "
                "the login."
            )
        emit(
            LoginReport(url=stored.base_url, identity=identity),
            f"Logged in to {stored.base_url} as {_who(identity)}. This login is now the default.",
            json_output=json_output,
        )


@auth_app.command("status")
def status_command(url: UrlOption = None, json_output: JsonOption = False) -> None:
    """Show the deployment, the credential in use and who it belongs to."""
    with reporting(json_output=json_output):
        target = resolve_base_url(url)
        resolved = resolve_credential(target, token=None)
        match resolved:
            case FromStore():
                credential = CredentialReport(kind="stored_login", source=resolved.source)
                action = f"Run `wpvt auth login --url {target}`."
            case FromEnvironment() | FromArgument():
                credential = CredentialReport(kind="api_token", source=resolved.source)
                action = f"Check the token in {TOKEN_ENV_VAR}."
        try:
            identity = _identity(resolved.credential, target)
        except AuthError as exc:
            raise AuthError(
                f"{target} rejected the credential: {exc.message}. {action}", exc.status_code
            ) from exc
        emit(
            StatusReport(url=target, credential=credential, identity=identity),
            "\n".join(
                [
                    f"Deployment: {target}",
                    f"Credential: {_describe(credential)}",
                    f"Identity:   {_who(identity)}",
                    f"Scopes:     {', '.join(identity.scopes) or '(none)'}",
                ]
            ),
            json_output=json_output,
        )


@auth_app.command("logout")
def logout_command(
    url: UrlOption = None,
    all_logins: Annotated[bool, typer.Option("--all", help="Remove every stored login.")] = False,
    json_output: JsonOption = False,
) -> None:
    """Remove the stored login and revoke its refresh token where the server allows it."""
    with reporting(json_output=json_output):
        if all_logins and url is not None:
            raise ConfigurationError("Pass either --url or --all, not both.")
        if all_logins:
            removed = logout_all()
        else:
            result = logout(resolve_base_url(url))
            removed = [] if result is None else [result]
        lines = [f"Logged out of {item.url}; {_revocation(item)}." for item in removed]
        emit(
            LogoutReport(removed=removed),
            "\n".join(lines) or "No stored login to remove.",
            json_output=json_output,
        )


def _identity(credential: Credential, base_url: str) -> Identity:
    transport = HTTPTransport(credential, base_url)
    try:
        return Me(transport).get()
    finally:
        transport.close()


def _who(identity: Identity) -> str:
    match identity:
        case ApiTokenIdentity() | UserTokenIdentity():
            person = identity.name or str(identity.user_id)
            email = f" <{identity.email}>" if identity.email else ""
            role = f" (role: {identity.role})" if identity.role else ""
            return f"{person}{email}{role}"
        case LegacyClientIdentity():
            return f"legacy client {identity.client_id or '(unknown)'}"


def _describe(credential: CredentialReport) -> str:
    match credential.source:
        case "store":
            return "stored login (wpvt auth login)"
        case "environment":
            return f"API token from {TOKEN_ENV_VAR}"
        case "argument":
            return "API token argument"


def _revocation(item: LoggedOut) -> str:
    match item.revocation:
        case "revoked":
            return "the refresh token was revoked"
        case "not_offered":
            return (
                "the authorization server offers no revocation, so the refresh token stays "
                "valid until it expires"
            )
        case "failed":
            return "revoking the refresh token failed, so it stays valid until it expires"
        case "skipped":
            return "its tokens could not be read, so nothing was revoked"

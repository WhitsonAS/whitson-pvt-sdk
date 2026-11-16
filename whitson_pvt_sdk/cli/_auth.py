import os
import sys
import webbrowser
from typing import Annotated, Literal

import typer
from pydantic import BaseModel

from whitson_pvt_sdk._store import KEYRING_SERVICE, keyring_names
from whitson_pvt_sdk.auth import (
    TOKEN_ENV_VAR,
    URL_ENV_VAR,
    FromArgument,
    FromEnvironment,
    FromStore,
    ResolvedCredential,
    resolve_base_url,
    resolve_credential,
)
from whitson_pvt_sdk.cli._output import JsonOption, emit, note, reporting
from whitson_pvt_sdk.credentials import Credential
from whitson_pvt_sdk.errors import AuthError, ConfigurationError
from whitson_pvt_sdk.http import HTTPTransport
from whitson_pvt_sdk.login import (
    BrowserLogin,
    Confirmation,
    DeviceLogin,
    LoggedOut,
    login,
    logout,
    logout_all,
)
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
    trust_host: Annotated[
        bool,
        typer.Option(
            "--trust-host",
            help="Log in to the --url host although it is not a whitson PVT deployment "
            "(*.pvt.whitson.com) or this machine. Only for a host you know and trust.",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Answer yes to the question asked before the first login to a --trust-host "
            "deployment, or to a localhost one that names a login server other than whitson's, "
            "and after its login server changed. Required there without a terminal. It never "
            "answers a question about access to another service: that needs a terminal.",
        ),
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Log in through the browser (or --device) and make this login the default."""
    with reporting(json_output=json_output):
        if trust_host and url is None:
            raise ConfigurationError("--trust-host applies only to a URL given with --url.")
        target = resolve_base_url(url).url
        interactive = sys.stdin.isatty() and sys.stderr.isatty()
        if device:
            method: BrowserLogin | DeviceLogin = DeviceLogin()
        elif interactive:
            method = BrowserLogin(open_browser=_open_browser)
        else:
            note("No terminal is attached, so no browser is opened.")
            method = BrowserLogin()

        def confirm(confirmation: Confirmation) -> bool:
            note(confirmation.describe())
            foreign = confirmation.foreign_audience is not None
            if yes and foreign:
                raise ConfigurationError(
                    "--yes does not accept access to another service. Run the login again "
                    "without --yes, in a terminal, and answer the question yourself."
                )
            if yes:
                return True
            if not interactive:
                raise ConfigurationError(
                    "Confirming access to another service needs a terminal; run the login in one."
                    if foreign
                    else "Confirming a login needs a terminal. Check the hosts above and pass "
                    "--yes to continue."
                )
            return typer.confirm("Continue?", default=False, err=True)

        report = login(
            target,
            method,
            output=note,
            verify=lambda stored: LoginReport(
                url=stored.base_url, identity=_identity(stored, stored.base_url)
            ),
            confirm=confirm,
            trust_host=trust_host,
        )
        if TOKEN_ENV_VAR in os.environ:
            note(
                f"{TOKEN_ENV_VAR} is set: commands given a URL (--url or {URL_ENV_VAR}) use it "
                "instead of this login, and commands without one refuse to run. Unset it to use "
                "the login."
            )
        emit(
            report,
            f"Logged in to {report.url} as {_who(report.identity)}. This login is now the default.",
            json_output=json_output,
        )


@auth_app.command("status")
def status_command(url: UrlOption = None, json_output: JsonOption = False) -> None:
    """Show the deployment, the credential in use and who it belongs to."""
    with reporting(json_output=json_output):
        resolved = resolve_credential(url, token=None)
        target = resolved.url
        match resolved:
            case FromStore():
                credential = CredentialReport(kind="stored_login", source=resolved.source)
            case FromEnvironment() | FromArgument():
                credential = CredentialReport(kind="api_token", source=resolved.source)
        try:
            identity = _identity(resolved.credential, target)
        except AuthError as exc:
            raise AuthError(
                f"{target} rejected the credential: {exc.message}.{_next_step(resolved, exc)}",
                exc.status_code,
            ) from exc
        emit(
            StatusReport(url=target, credential=credential, identity=identity),
            "\n".join(
                [
                    f"Deployment: {target}",
                    f"Credential: {_describe(credential)}",
                    f"Identity:   {_who(identity)}",
                    f"Scopes:     {_scopes(identity)}",
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
            result = logout(resolve_base_url(url).url)
            removed = [] if result is None else [result]
        lines = [
            f"Logged out of {item.url}; {_revocation(item)}.{_keyring_cleanup(item)}"
            for item in removed
        ]
        emit(
            LogoutReport(removed=removed),
            "\n".join(lines) or "No stored login to remove.",
            json_output=json_output,
        )


def _open_browser(url: str) -> bool:
    # A browser started on Linux inherits descriptors 1 and 2 and logs to the terminal through them.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            stream.flush()
    saved: list[tuple[int, int]] = []
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        for descriptor in (1, 2):
            try:
                saved.append((descriptor, os.dup(descriptor)))
            except OSError:
                continue
            os.dup2(devnull, descriptor)
        return webbrowser.open(url)
    finally:
        for descriptor, copy in saved:
            os.dup2(copy, descriptor)
            os.close(copy)
        os.close(devnull)


def _identity(credential: Credential, base_url: str) -> Identity:
    transport = HTTPTransport(credential, base_url)
    try:
        return Me(transport).get()
    finally:
        transport.close()


def _next_step(resolved: ResolvedCredential, refusal: AuthError) -> str:
    match resolved:
        case FromStore() if refusal.server_message is None:
            return f" Run `wpvt auth login --url {resolved.url}`."
        case FromStore():
            return ""
        case FromEnvironment() | FromArgument():
            return f" Check the token in {TOKEN_ENV_VAR}."


def _who(identity: Identity) -> str:
    match identity:
        case ApiTokenIdentity():
            return f'{_person(identity)}, API token "{identity.token_name}"'
        case UserTokenIdentity():
            return _person(identity)
        case LegacyClientIdentity():
            return f"legacy client {identity.client_subject or '(unknown)'}, full access"


def _person(identity: ApiTokenIdentity | UserTokenIdentity) -> str:
    email = f" <{identity.email}>" if identity.email else ""
    return f"{identity.name or f'user {identity.user_id}'}{email} (role: {identity.role})"


def _scopes(identity: Identity) -> str:
    match identity:
        case ApiTokenIdentity() | UserTokenIdentity():
            return ", ".join(identity.scopes) or "(none)"
        case LegacyClientIdentity():
            return "all (legacy client)"


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


def _keyring_cleanup(item: LoggedOut) -> str:
    match item.keyring:
        case "not_used" | "deleted":
            return ""
        case "not_deleted":
            access_name, refresh_name = keyring_names(item.url)
            return (
                " Its tokens could not be deleted from the OS keyring; remove the entries "
                f'"{access_name}" and "{refresh_name}" of the service "{KEYRING_SERVICE}" with '
                "your keyring tool."
            )

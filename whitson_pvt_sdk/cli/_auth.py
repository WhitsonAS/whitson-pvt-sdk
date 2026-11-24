import os
import re
import sys
import webbrowser
from collections.abc import Callable
from functools import partial
from typing import Annotated, Literal

import typer
from pydantic import BaseModel, computed_field

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
from whitson_pvt_sdk.errors import AuthError, ConfigurationError, LoginError
from whitson_pvt_sdk.http import HTTPTransport
from whitson_pvt_sdk.login import (
    READ_SCOPES,
    AllScopes,
    BrowserLogin,
    BrowserOpened,
    ChosenScopes,
    Confirmation,
    DeviceCode,
    DeviceLogin,
    LoggedOut,
    LoginMethod,
    NewLogin,
    NoBrowser,
    Notice,
    PickScopes,
    ScopeChoice,
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


class NotGranted(BaseModel):
    by_server: list[str]
    by_role: list[str]


class LoginReport(BaseModel):
    url: str
    identity: Identity
    not_granted: NotGranted


class CredentialReport(BaseModel):
    source: Literal["argument", "environment", "store"]

    @computed_field
    @property
    def kind(self) -> Literal["api_token", "stored_login"]:
        match self.source:
            case "store":
                return "stored_login"
            case "argument" | "environment":
                return "api_token"


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
            "--device",
            help="Log in with a code confirmed in a browser on any device. Used without this "
            "option too when no browser can be opened here or no terminal is attached.",
        ),
    ] = False,
    email: Annotated[
        str | None,
        typer.Option(
            "--email",
            help="Keep the login only if it is for this account; otherwise discard it, revoke "
            "it and store nothing.",
        ),
    ] = None,
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
    scope: Annotated[
        list[str] | None,
        typer.Option(
            "--scope",
            help=f'Request only this scope; repeat for more. "{READ_SCOPES}" stands for every '
            "*:read scope. Without it, the scopes are chosen before signing in, all of them "
            "ticked: on a page in the browser, or at the terminal when logging in with a code; "
            "without a terminal every scope the deployment offers is requested. offline_access "
            "is always requested. Your role can still narrow what is granted.",
        ),
    ] = None,
    json_output: JsonOption = False,
) -> None:
    """Log in through the browser (or with a code) and make this login the default."""
    with reporting(json_output=json_output):
        if trust_host and url is None:
            raise ConfigurationError("--trust-host applies only to a URL given with --url.")
        target = resolve_base_url(url).url
        interactive = sys.stdin.isatty() and sys.stderr.isatty()
        if scope:
            scopes: ScopeChoice = ChosenScopes(names=frozenset(scope))
        elif interactive:
            scopes = PickScopes(ask=_ask_at_terminal)
        else:
            scopes = AllScopes()

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

        if device:
            method: LoginMethod = DeviceLogin()
        elif interactive:
            method = BrowserLogin(open_browser=_open_browser)
        else:
            note(
                "No terminal is attached, so logging in with a code: pass the link and code "
                "below to the person who logs in."
            )
            method = DeviceLogin()

        def show(notice: Notice) -> None:
            match notice:
                case DeviceCode() if json_output:
                    note(notice.model_dump_json())
                case DeviceCode():
                    note(notice.message)
                case str():
                    note(notice)

        report = login(
            target,
            method,
            output=show,
            verify=partial(_login_report, email=None if email is None else email.strip()),
            scopes=scopes,
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
            f"Logged in to {report.url} as {_who(report.identity)}. This login is now the default."
            + _narrower(report),
            json_output=json_output,
        )


@auth_app.command("status")
def status_command(url: UrlOption = None, json_output: JsonOption = False) -> None:
    """Show the deployment, the credential in use and who it belongs to."""
    with reporting(json_output=json_output):
        resolved = resolve_credential(url, token=None)
        target = resolved.url
        credential = CredentialReport(source=resolved.source)
        identity = _identity(
            resolved.credential,
            target,
            rejected="the credential",
            next_step=partial(_next_step, resolved),
        )
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


def _open_browser(url: str) -> BrowserOpened | NoBrowser:
    environ = os.environ
    if not (environ.get("DISPLAY") or environ.get("WAYLAND_DISPLAY") or environ.get("BROWSER")):
        if environ.get("SSH_CONNECTION") or environ.get("SSH_TTY"):
            return NoBrowser(reason="This SSH session has no display")
        if sys.platform not in ("win32", "darwin"):
            return NoBrowser(reason="There is no display (DISPLAY and WAYLAND_DISPLAY are unset)")
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
        opened = webbrowser.open(url)
    except (webbrowser.Error, OSError) as exc:
        return NoBrowser(reason=f"No browser could be started ({exc})")
    finally:
        for descriptor, copy in saved:
            os.dup2(copy, descriptor)
            os.close(copy)
        os.close(devnull)
    return BrowserOpened() if opened else NoBrowser(reason="No browser could be started")


def _ask_at_terminal(offered: tuple[str, ...]) -> list[str]:
    note("\n".join(f"{number:>3}. {name}" for number, name in enumerate(offered, start=1)))
    answer: str = typer.prompt(
        f'Scopes to request: numbers or names, "{READ_SCOPES}" for every *:read scope; '
        "Enter for all",
        default="",
        show_default=False,
        err=True,
    )
    words = [word for word in re.split(r"[\s,]+", answer) if word]
    if not words:
        return list(offered)
    return [
        offered[int(word) - 1] if word.isdecimal() and 1 <= int(word) <= len(offered) else word
        for word in words
    ]


def _login_report(new: NewLogin, *, email: str | None) -> LoginReport:
    identity = _identity(new.credential, new.url, rejected="the new login")
    match identity:
        case ApiTokenIdentity() | UserTokenIdentity():
            by_role = [scope for scope in new.granted if scope not in identity.scopes]
            account = (identity.email or "").strip().casefold()
        case LegacyClientIdentity():
            by_role = []
            account = None
    if email is not None and account != email.casefold():
        raise LoginError(
            f"Signed in as {_who(identity)}, not {email} as --email expects. The login was "
            f"discarded and nothing was stored; log in again with the account {email}."
        )
    return LoginReport(
        url=new.url,
        identity=identity,
        not_granted=NotGranted(
            by_server=[scope for scope in new.scopes if scope not in new.granted],
            by_role=by_role,
        ),
    )


def _narrower(report: LoginReport) -> str:
    missing = report.not_granted
    lines = []
    if missing.by_server:
        lines.append(
            f"Not granted by the login server: {', '.join(missing.by_server)}. It left them out "
            "of the token, so logging in again does not add them; ask the administrator of "
            f"{report.url} about them."
        )
    if missing.by_role:
        lines.append(
            f"Not granted: {', '.join(missing.by_role)}. Your role on {report.url} does not "
            "allow them, so logging in again does not add them."
        )
    return "".join(f"\n{line}" for line in lines)


def _identity(
    credential: Credential,
    base_url: str,
    *,
    rejected: str,
    next_step: Callable[[AuthError], str] = lambda _: "",
) -> Identity:
    transport = HTTPTransport(credential, base_url)
    try:
        return Me(transport).get()
    except AuthError as exc:
        raise AuthError(
            f"{base_url} rejected {rejected}: {exc.message.rstrip('.')}.{next_step(exc)}",
            exc.status_code,
            request_id=exc.request_id,
        ) from exc
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

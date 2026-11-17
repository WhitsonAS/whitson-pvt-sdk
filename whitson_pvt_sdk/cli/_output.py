import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Literal

import typer
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from whitson_pvt_sdk.cli import ExitCode
from whitson_pvt_sdk.errors import (
    AuthError,
    ConfigurationError,
    LoginError,
    NoResponseError,
    RequestRefusedError,
    ResponseError,
    SDKError,
)

JsonOption = Annotated[bool, typer.Option("--json", help="Print one JSON document on stdout.")]

ErrorKind = Literal["configuration", "authentication", "network", "server", "refused", "error"]


class FileReport(BaseModel):
    path: str


class ErrorReport(BaseModel):
    error: ErrorKind
    message: str


class ResponseErrorReport(ErrorReport):
    status: int
    request_id: str | None


_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def _printable(text: str) -> str:
    return _CONTROL.sub(lambda match: f"\\x{ord(match.group()):02x}", text)


def note(message: str) -> None:
    typer.echo(_printable(message), err=True)


def emit(report: BaseModel, text: str, *, json_output: bool) -> None:
    typer.echo(report.model_dump_json(indent=2) if json_output else _printable(text))


def emit_data(data: BaseModel) -> None:
    typer.echo(data.model_dump_json(indent=2))


class _NoteHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        note(self.format(record))


_SDK_LOGGER = logging.getLogger("whitson_pvt_sdk")


@contextmanager
def reporting(*, json_output: bool) -> Iterator[None]:
    # Without a handler, Python's last-resort handler would print SDK warnings unescaped, and
    # with --json they would break the one JSON document on stderr.
    log_handler = logging.NullHandler() if json_output else _NoteHandler()
    _SDK_LOGGER.addHandler(log_handler)
    try:
        yield
    except (SDKError, PydanticValidationError) as exc:
        report = _report(exc)
        typer.echo(
            report.model_dump_json() if json_output else _printable(f"Error: {report.message}"),
            err=True,
        )
        raise typer.Exit(_exit_code(report.error)) from None
    finally:
        _SDK_LOGGER.removeHandler(log_handler)


def _report(exc: SDKError | PydanticValidationError) -> ErrorReport:
    match exc:
        case ConfigurationError():
            return ErrorReport(error="configuration", message=exc.message)
        case LoginError():
            return ErrorReport(error="authentication", message=exc.message)
        case NoResponseError():
            return ErrorReport(error="network", message=exc.message)
        case AuthError():
            return _response_report("authentication", exc)
        case RequestRefusedError():
            return _response_report("refused", exc)
        case ResponseError():
            return _response_report("server", exc)
        case SDKError():
            return ErrorReport(error="error", message=exc.message)
        case PydanticValidationError():
            return ErrorReport(error="server", message=f"Unexpected response from the API: {exc}")


def _exit_code(kind: ErrorKind) -> ExitCode:
    match kind:
        case "configuration":
            return ExitCode.USAGE
        case "authentication":
            return ExitCode.AUTHENTICATION
        case "network" | "server":
            return ExitCode.SERVER
        case "refused":
            return ExitCode.REFUSED
        case "error":
            return ExitCode.ERROR


def _response_report(kind: ErrorKind, exc: ResponseError) -> ResponseErrorReport:
    return ResponseErrorReport(
        error=kind, message=exc.message, status=exc.status_code, request_id=exc.request_id
    )

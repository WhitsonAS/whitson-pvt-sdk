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
    ResponseError,
    SDKError,
)

JsonOption = Annotated[bool, typer.Option("--json", help="Print one JSON document on stdout.")]

ErrorKind = Literal["configuration", "authentication", "network", "server", "error"]


class FileReport(BaseModel):
    path: str


class ErrorReport(BaseModel):
    error: ErrorKind
    message: str


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
    except ConfigurationError as exc:
        _fail("configuration", exc.message, ExitCode.USAGE, json_output)
    except (LoginError, AuthError) as exc:
        _fail("authentication", exc.message, ExitCode.AUTHENTICATION, json_output)
    except NoResponseError as exc:
        _fail("network", exc.message, ExitCode.SERVER, json_output)
    except ResponseError as exc:
        _fail("server", exc.message, ExitCode.SERVER, json_output)
    except SDKError as exc:
        _fail("error", exc.message, ExitCode.ERROR, json_output)
    except PydanticValidationError as exc:
        _fail("server", f"Unexpected response from the API: {exc}", ExitCode.SERVER, json_output)
    finally:
        _SDK_LOGGER.removeHandler(log_handler)


def _fail(kind: ErrorKind, message: str, code: ExitCode, json_output: bool) -> None:
    report = ErrorReport(error=kind, message=message)
    typer.echo(
        report.model_dump_json() if json_output else _printable(f"Error: {message}"), err=True
    )
    raise typer.Exit(code)

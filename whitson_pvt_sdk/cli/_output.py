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


def note(message: str) -> None:
    typer.echo(message, err=True)


def emit(report: BaseModel, text: str, *, json_output: bool) -> None:
    typer.echo(report.model_dump_json(indent=2) if json_output else text)


def emit_data(data: BaseModel) -> None:
    typer.echo(data.model_dump_json(indent=2))


@contextmanager
def reporting(*, json_output: bool) -> Iterator[None]:
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
        _fail("error", exc.message, 1, json_output)
    except PydanticValidationError as exc:
        _fail("server", f"Unexpected response from the API: {exc}", ExitCode.SERVER, json_output)


def _fail(kind: ErrorKind, message: str, code: int, json_output: bool) -> None:
    report = ErrorReport(error=kind, message=message)
    typer.echo(report.model_dump_json() if json_output else f"Error: {message}", err=True)
    raise typer.Exit(code)

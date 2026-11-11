from typing import Annotated

import typer

from whitson_pvt_sdk import __version__
from whitson_pvt_sdk.cli._auth import auth_app

app = typer.Typer(
    name="wpvt",
    help="Command line for the whitson PVT external API.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(auth_app, name="auth")


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"wpvt {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_print_version, is_eager=True, help="Print the version."
        ),
    ] = False,
) -> None:
    return

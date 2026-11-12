from typing import Annotated

import typer

from whitson_pvt_sdk import __version__
from whitson_pvt_sdk.cli._api import api_command
from whitson_pvt_sdk.cli._auth import UrlOption, auth_app
from whitson_pvt_sdk.cli._calc import calc_app
from whitson_pvt_sdk.cli._output import reporting
from whitson_pvt_sdk.cli._reports import reports_app
from whitson_pvt_sdk.cli._resources import RESOURCES, resource_app

app = typer.Typer(
    name="wpvt",
    help="Command line for the whitson PVT external API.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(auth_app, name="auth")
for resource in RESOURCES:
    app.add_typer(resource_app(resource), name=resource.name)
app.add_typer(reports_app, name="reports")
app.add_typer(calc_app, name="calc")
app.command("api")(api_command)


@app.command("mcp")
def mcp_command(
    url: UrlOption = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", help="Log more to stderr (never tokens).")
    ] = False,
) -> None:
    """Serve the deployment's MCP tools on stdio for an agent host, with your wpvt login.

    Add it with `claude mcp add wpvt -- wpvt mcp` or `codex mcp add wpvt -- wpvt mcp`.
    It never starts a login: run `wpvt auth login` first.
    """
    with reporting(json_output=False):
        from whitson_pvt_sdk.cli._mcp import serve

        serve(url, verbose=verbose)


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

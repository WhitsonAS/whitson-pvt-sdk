from pathlib import Path
from typing import Annotated

import typer

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.cli._output import FileReport, JsonOption, emit, emit_data, reporting
from whitson_pvt_sdk.shared.models import ImportArchiveOptions

reports_app = typer.Typer(help="Export and import report archives.", no_args_is_help=True)


class ArchiveReport(FileReport):
    bytes: int


@reports_app.command("export")
def export_report(
    report_id: Annotated[int, typer.Argument(metavar="REPORT_ID", help="The report's id.")],
    out: Annotated[Path, typer.Option("--out", dir_okay=False, help="Zip file to write.")],
    archive_format: Annotated[
        str | None,
        typer.Option("--format", help="Archive format, such as osdu; the native format otherwise."),
    ] = None,
    native_payload: Annotated[
        bool,
        typer.Option("--native-payload", help="Include the whitson native payload (OSDU)."),
    ] = False,
    structured_experiments: Annotated[
        bool,
        typer.Option("--structured-experiments", help="Include structured experiments (OSDU)."),
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Download a report archive to a zip file."""
    with reporting(json_output=json_output), WhitsonPVTClient() as client:
        content, _ = client.reports.export(
            report_id,
            format=archive_format,
            include_whitson_native_payload=native_payload or None,
            include_structured_experiments=structured_experiments or None,
        )
        out.write_bytes(content)
        emit(
            ArchiveReport(path=str(out), bytes=len(content)),
            f"Wrote {out} ({len(content)} bytes)",
            json_output=json_output,
        )


@reports_app.command("import")
def import_report(
    archive: Annotated[
        Path, typer.Argument(metavar="FILE", exists=True, dir_okay=False, help="Zip archive.")
    ],
    region_id: Annotated[
        int | None, typer.Option("--region", help="Region to import into.")
    ] = None,
    acknowledge_suggestions: Annotated[
        bool, typer.Option("--acknowledge-suggestions", help="Accept the import's suggestions.")
    ] = False,
    preflight: Annotated[
        bool, typer.Option("--preflight", help="Only check the archive; import nothing.")
    ] = False,
) -> None:
    """Import a report archive and print the result as JSON."""
    options = ImportArchiveOptions(
        region_id=region_id, acknowledge_suggestions=acknowledge_suggestions
    )
    with reporting(json_output=False), WhitsonPVTClient() as client:
        content = archive.read_bytes()
        if preflight:
            emit_data(client.reports.preflight_import(content, options))
        else:
            emit_data(client.reports.import_archive(content, options))

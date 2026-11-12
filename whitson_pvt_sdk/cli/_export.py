import csv
import io
import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

import typer
from pydantic import AwareDatetime, BaseModel

from whitson_pvt_sdk import WhitsonPVTClient, __version__
from whitson_pvt_sdk.cli._output import JsonOption, emit, reporting
from whitson_pvt_sdk.errors import ConfigurationError
from whitson_pvt_sdk.v2.models import (
    BlackOilTableRowModel,
    CompositionModel,
    GetBlackOilTableModel,
    GetSampleModel,
)

UNITS = (
    "Values are in the units the API returns. A quantity's unit is in the field named after it "
    "with _unit appended, in the same object (sample.json, an experiment, or a black-oil table)."
)


class CompositionFile(BaseModel):
    field: str
    file: str


class ExperimentFile(BaseModel):
    position: int
    type: str
    name: str
    file: str


class SampleIndex(BaseModel):
    format: Literal["wpvt-sample-export/1"] = "wpvt-sample-export/1"
    sample_id: int
    sample_name: str | None
    sdk_version: str
    api_version: Literal["external/v2"] = "external/v2"
    exported_at: AwareDatetime
    units: str = UNITS
    header: Literal["sample.json"] = "sample.json"
    compositions: list[CompositionFile]
    experiments: list[ExperimentFile]


class SampleExport(BaseModel):
    sample_id: int
    directory: str


class SamplesExportReport(BaseModel):
    samples: list[SampleExport]


class FileReport(BaseModel):
    path: str


def export_samples(
    sample_ids: Annotated[list[int], typer.Argument(metavar="ID", help="Sample ids.")],
    out: Annotated[
        Path,
        typer.Option(
            "--out", file_okay=False, help="Directory that receives one directory per id."
        ),
    ],
    force: Annotated[
        bool, typer.Option("--force", help="Replace sample directories that are not empty.")
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Write each sample to DIR/ID/: sample.json, compositions/, experiments/ and index.json."""
    with reporting(json_output=json_output):
        targets = [(sample_id, out / str(sample_id)) for sample_id in dict.fromkeys(sample_ids)]
        occupied = [str(target) for _, target in targets if _occupied(target)]
        if occupied and not force:
            raise ConfigurationError(
                f"Not empty: {', '.join(occupied)}. Pass --force to replace them."
            )
        out.mkdir(parents=True, exist_ok=True)
        with WhitsonPVTClient() as client:
            for sample_id, target in targets:
                _replace_directory(target, _sample_files(client.samples.get(sample_id)))
        emit(
            SamplesExportReport(
                samples=[SampleExport(sample_id=id, directory=str(path)) for id, path in targets]
            ),
            "\n".join(f"Wrote sample {id} to {path}" for id, path in targets),
            json_output=json_output,
        )


def export_black_oil_table(
    table_id: Annotated[int, typer.Argument(metavar="ID", help="The black-oil table's id.")],
    out: Annotated[Path, typer.Option("--out", dir_okay=False, help="File to write.")],
    file_format: Annotated[
        Literal["json", "csv"],
        typer.Option("--format", help="json: the whole table; csv: its rows, units in the header."),
    ] = "json",
    json_output: JsonOption = False,
) -> None:
    """Write the full black-oil table, every row, to a file."""
    with reporting(json_output=json_output), WhitsonPVTClient() as client:
        table = client.black_oil_tables.get(table_id)
        match file_format:
            case "json":
                out.write_text(table.model_dump_json(indent=2) + "\n")
            case "csv":
                out.write_text(_table_csv(table))
        emit(FileReport(path=str(out)), f"Wrote {out}", json_output=json_output)


def _occupied(target: Path) -> bool:
    return target.exists() and (not target.is_dir() or any(target.iterdir()))


def _sample_files(sample: GetSampleModel) -> dict[str, str]:
    compositions = {
        name: value
        for name in type(sample).model_fields
        if isinstance(value := getattr(sample, name), CompositionModel)
    }
    experiments = sample.experiments or []
    width = len(str(len(experiments)))
    experiment_files = [
        ExperimentFile(
            position=position,
            type=experiment.type,
            name=experiment.name,
            file=f"experiments/{position:0{width}d}-{experiment.type}.json",
        )
        for position, experiment in enumerate(experiments, start=1)
    ]
    index = SampleIndex(
        sample_id=sample.id,
        sample_name=sample.name,
        sdk_version=__version__,
        exported_at=datetime.now(UTC),
        compositions=[
            CompositionFile(field=name, file=f"compositions/{name}.json") for name in compositions
        ],
        experiments=experiment_files,
    )
    files = {
        "index.json": index.model_dump_json(indent=2),
        "sample.json": sample.model_dump_json(indent=2, exclude={*compositions, "experiments"}),
    }
    for entry in index.compositions:
        files[entry.file] = compositions[entry.field].model_dump_json(indent=2)
    for entry, experiment in zip(experiment_files, experiments, strict=True):
        files[entry.file] = experiment.model_dump_json(indent=2)
    return files


def _replace_directory(target: Path, files: dict[str, str]) -> None:
    staging = target.with_name(f".{target.name}.{secrets.token_hex(4)}.partial")
    try:
        for name, content in files.items():
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content + "\n")
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        elif target.exists() or target.is_symlink():
            target.unlink()
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _table_csv(table: GetBlackOilTableModel) -> str:
    fields = table.model_dump(mode="json")
    columns = {
        column: f"{column} [{fields[f'{column}_unit']}]" if f"{column}_unit" in fields else column
        for column in BlackOilTableRowModel.model_fields
    }
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns.values())
    for row in table.rows:
        values = row.model_dump(mode="json")
        writer.writerow(values[column] for column in columns)
    return buffer.getvalue()

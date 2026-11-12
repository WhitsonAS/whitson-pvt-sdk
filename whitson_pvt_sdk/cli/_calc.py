import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Generic, TypeVar

import typer
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.cli._output import FileReport, JsonOption, emit, emit_data, reporting
from whitson_pvt_sdk.errors import ConfigurationError
from whitson_pvt_sdk.shared.models import CompositionSource
from whitson_pvt_sdk.v2.models import (
    FlashCalculationRequestModel,
    PhaseEnvelopeCalculationRequestModel,
    SaturationPressureCalculationRequestModel,
)
from whitson_pvt_sdk.v2.resources import Calculations

calc_app = typer.Typer(
    help="Run a synchronous calculation from a JSON request.", no_args_is_help=True
)

Request = TypeVar("Request", bound=BaseModel)


class Calculation(BaseModel, Generic[Request]):
    model_config = ConfigDict(frozen=True)

    name: str
    help: str
    request: type[Request]
    run: Callable[[Calculations, Request], BaseModel]


class RequestFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str


class _SampleConditions(BaseModel):
    inputs: list[dict[str, JsonValue]] = [{}]


_json_object: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])


class SampleFeed(BaseModel):
    model_config = ConfigDict(frozen=True)

    sample_id: int
    fluid_model_id: int
    source: CompositionSource
    conditions: str | None


InputOption = Annotated[
    str | None,
    typer.Option(
        "--input",
        metavar="FILE",
        help="The request as JSON, or - for stdin. With --sample, the request without "
        "fluid_model_id and without feed_composition in its inputs.",
    ),
]
SampleOption = Annotated[
    int | None,
    typer.Option("--sample", help="Use this stored sample's composition as the feed."),
]
FluidModelOption = Annotated[
    int | None, typer.Option("--fluid-model", help="Fluid model for --sample.")
]
SourceOption = Annotated[
    CompositionSource | None,
    typer.Option(
        "--source",
        help="Feed from the sample-to-EOS slate conversion (default) or the fluid model's "
        "adjusted compositions. Only with --sample.",
    ),
]
OutOption = Annotated[
    Path | None,
    typer.Option("--out", dir_okay=False, help="Write the response here instead of stdout."),
]


def _register(calculation: Calculation[Request]) -> None:
    def command(
        input_file: InputOption = None,
        sample: SampleOption = None,
        fluid_model: FluidModelOption = None,
        source: SourceOption = None,
        out: OutOption = None,
        json_output: JsonOption = False,
    ) -> None:
        with reporting(json_output=json_output):
            origin = _request_origin(input_file, sample, fluid_model, source)
            with WhitsonPVTClient() as client:
                request = _request(calculation.request, origin, client.calculations)
                response = calculation.run(client.calculations, request)
            if out is None:
                emit_data(response)
            else:
                out.write_text(response.model_dump_json(indent=2) + "\n")
                emit(FileReport(path=str(out)), f"Wrote {out}", json_output=json_output)

    calc_app.command(calculation.name, help=calculation.help)(command)


def _request_origin(
    input_file: str | None,
    sample: int | None,
    fluid_model: int | None,
    source: CompositionSource | None,
) -> RequestFile | SampleFeed:
    match (input_file, sample, fluid_model, source):
        case (str() as path, None, None, None):
            return RequestFile(path=path)
        case (_, int() as sample_id, int() as fluid_model_id, _):
            return SampleFeed(
                sample_id=sample_id,
                fluid_model_id=fluid_model_id,
                source=source or "slate_to_slate_converted",
                conditions=input_file,
            )
        case (_, int(), None, _) | (_, None, int(), _):
            raise ConfigurationError("--sample and --fluid-model go together.")
        case (_, None, None, str()):
            raise ConfigurationError("--source applies only with --sample and --fluid-model.")
        case _:
            raise ConfigurationError("Pass --input FILE, or --sample ID --fluid-model ID.")


def _request(
    model: type[Request], origin: RequestFile | SampleFeed, calculations: Calculations
) -> Request:
    match origin:
        case RequestFile(path=path):
            return _validated(model, _read_object(path))
        case SampleFeed(conditions=conditions) as feed:
            document = {} if conditions is None else _read_object(conditions)
            try:
                rest = _SampleConditions.model_validate(document)
            except PydanticValidationError:
                rest = None
            if rest is None or "fluid_model_id" in document:
                raise ConfigurationError(
                    "With --sample, the request file must not set fluid_model_id (it comes "
                    "from --fluid-model) and its inputs must be a list of objects."
                )
            if any("feed_composition" in item for item in rest.inputs):
                raise ConfigurationError(
                    "With --sample, leave feed_composition out of the inputs; it comes from "
                    "the sample."
                )
            composition = calculations.get_sample_feed_composition(
                feed.fluid_model_id, feed.sample_id, feed.source
            )
            feed_composition = [entry.model_dump(mode="json") for entry in composition]
            return _validated(
                model,
                {
                    **document,
                    "fluid_model_id": feed.fluid_model_id,
                    "inputs": [
                        {**item, "feed_composition": feed_composition} for item in rest.inputs
                    ],
                },
            )


def _read_object(path: str) -> dict[str, JsonValue]:
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text()
    except OSError as exc:
        raise ConfigurationError(f"Cannot read {path}: {exc.strerror}.") from None
    try:
        return _json_object.validate_json(text)
    except PydanticValidationError:
        raise ConfigurationError(f"{path} must hold a JSON object.") from None


def _validated(model: type[Request], document: dict[str, JsonValue]) -> Request:
    try:
        return model.model_validate(document)
    except PydanticValidationError as exc:
        raise ConfigurationError(f"The request is not a valid {model.__name__}:\n{exc}") from None


_register(
    Calculation[FlashCalculationRequestModel](
        name="flash",
        help="Flash a feed at pressure and temperature.",
        request=FlashCalculationRequestModel,
        run=Calculations.calculate_flash,
    )
)
_register(
    Calculation[SaturationPressureCalculationRequestModel](
        name="saturation-pressure",
        help="Saturation pressure of a feed at temperature.",
        request=SaturationPressureCalculationRequestModel,
        run=Calculations.calculate_saturation_pressure,
    )
)
_register(
    Calculation[PhaseEnvelopeCalculationRequestModel](
        name="phase-envelope",
        help="Phase envelope of a feed.",
        request=PhaseEnvelopeCalculationRequestModel,
        run=Calculations.calculate_phase_envelope,
    )
)

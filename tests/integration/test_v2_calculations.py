from collections.abc import Callable

import pytest

from whitson_pvt_sdk.errors import CalculationError
from whitson_pvt_sdk.v2 import WhitsonPVTClientV2
from whitson_pvt_sdk.v2.models import (
    FlashCalculationInputModel,
    FlashCalculationRequestModel,
    GorRecombinationCalculationInputModel,
    GorRecombinationCalculationRequestModel,
    PhaseEnvelopeCalculationInputModel,
    PhaseEnvelopeCalculationRequestModel,
    SampleToEosSlateConversionCalculationRequestModel,
    SaturationPressureCalculationInputModel,
    SaturationPressureCalculationRequestModel,
    SeparatorProcessCalculationInputModel,
    SeparatorProcessCalculationRequestModel,
    SurfaceProcessModel,
    SurfaceProcessStageModel,
)


@pytest.fixture(scope="session")
def feed_composition(
    client_v2: WhitsonPVTClientV2, require_id: Callable[[str], int], created_sample
):
    try:
        return client_v2.calculations.get_sample_feed_composition(
            fluid_model_id=require_id("FLUID_MODEL_ID"),
            sample_id=created_sample.id,
            source="slate_to_slate_converted",
        )
    except CalculationError as exc:
        pytest.skip(f"Sample/feed composition is incompatible with fluid model: {exc}")


@pytest.fixture(scope="session")
def surface_process() -> SurfaceProcessModel:
    return SurfaceProcessModel(
        pressure_unit="bara",
        temperature_unit="C",
        stages=[SurfaceProcessStageModel(pressure=1.01325, temperature=15.0)],
    )


def test_sample_to_eos_slate_conversion(
    client_v2: WhitsonPVTClientV2, require_id: Callable[[str], int], created_sample
):
    result = client_v2.calculations.calculate_sample_to_eos_slate_conversion(
        SampleToEosSlateConversionCalculationRequestModel(
            fluid_model_id=require_id("FLUID_MODEL_ID"),
            sample_ids=[created_sample.id],
        )
    )
    assert result.results


def test_get_sample_feed_composition(feed_composition):
    assert feed_composition


def test_flash_calculation(
    client_v2: WhitsonPVTClientV2,
    require_id: Callable[[str], int],
    feed_composition,
):
    result = client_v2.calculations.calculate_flash(
        FlashCalculationRequestModel(
            fluid_model_id=require_id("FLUID_MODEL_ID"),
            pressure_unit="bara",
            temperature_unit="C",
            inputs=[
                FlashCalculationInputModel(
                    pressure=50.0,
                    temperature=50.0,
                    feed_composition=feed_composition,
                )
            ],
        )
    )
    assert result.results


def test_saturation_pressure_calculation(
    client_v2: WhitsonPVTClientV2,
    require_id: Callable[[str], int],
    feed_composition,
):
    result = client_v2.calculations.calculate_saturation_pressure(
        SaturationPressureCalculationRequestModel(
            fluid_model_id=require_id("FLUID_MODEL_ID"),
            temperature_unit="C",
            inputs=[
                SaturationPressureCalculationInputModel(
                    temperature=50.0,
                    feed_composition=feed_composition,
                )
            ],
        )
    )
    assert result.results


def test_phase_envelope_calculation(
    client_v2: WhitsonPVTClientV2,
    require_id: Callable[[str], int],
    feed_composition,
):
    result = client_v2.calculations.calculate_phase_envelope(
        PhaseEnvelopeCalculationRequestModel(
            fluid_model_id=require_id("FLUID_MODEL_ID"),
            inputs=[PhaseEnvelopeCalculationInputModel(feed_composition=feed_composition)],
        )
    )
    assert result.results


def test_gor_recombination_calculation(
    client_v2: WhitsonPVTClientV2,
    require_id: Callable[[str], int],
    feed_composition,
    surface_process: SurfaceProcessModel,
):
    result = client_v2.calculations.calculate_gor_recombination(
        GorRecombinationCalculationRequestModel(
            fluid_model_id=require_id("FLUID_MODEL_ID"),
            recombination_type="total_gor",
            gor_unit="Sm3/m3",
            surface_process=surface_process,
            inputs=[
                GorRecombinationCalculationInputModel(
                    recombination_gor=100.0,
                    feed_composition=feed_composition,
                )
            ],
        )
    )
    assert result.results


def test_separator_process_calculation(
    client_v2: WhitsonPVTClientV2,
    require_id: Callable[[str], int],
    feed_composition,
    surface_process: SurfaceProcessModel,
):
    result = client_v2.calculations.calculate_separator_process(
        SeparatorProcessCalculationRequestModel(
            fluid_model_id=require_id("FLUID_MODEL_ID"),
            surface_process=surface_process,
            inputs=[SeparatorProcessCalculationInputModel(feed_composition=feed_composition)],
        )
    )
    assert result.results

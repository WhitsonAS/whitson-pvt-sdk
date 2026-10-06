from collections.abc import Callable

import pytest

from whitson_pvt_sdk.v2 import WhitsonPVTClientV2
from whitson_pvt_sdk.v2.models import (
    CalculationErrorResultModel,
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
    SurfaceProcessInputModel,
    SurfaceProcessStageInputModel,
    VolumetricToCompositionConversionCalculationRequestModel,
    VolumetricToCompositionConversionFluidModel,
    VolumetricToCompositionConversionInputModel,
)


@pytest.fixture(scope="session")
def feed_composition(client_v2: WhitsonPVTClientV2, require_id: Callable[[str], int]):
    # Independent of conversion: one backend error must not skip six other endpoints.
    return client_v2.calculations.get_sample_feed_composition(
        fluid_model_id=require_id("FLUID_MODEL_ID"),
        sample_id=require_id("SAMPLE_ID"),
        source="adjusted_compositions",
    )


@pytest.fixture(scope="session")
def surface_process() -> SurfaceProcessInputModel:
    return SurfaceProcessInputModel(
        pressure_unit="bara",
        temperature_unit="C",
        stages=[SurfaceProcessStageInputModel(pressure=1.01325, temperature=15.0)],
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
    assert len(result.results) == 1
    row = result.results[0]
    assert not isinstance(row, CalculationErrorResultModel), row.model_dump()
    assert sum(row.result.mole_fractions) == pytest.approx(1.0)
    assert sum(row.result.mass_fractions) == pytest.approx(1.0)


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
    assert len(result.results) == 1
    row = result.results[0]
    assert not isinstance(row, CalculationErrorResultModel), row.model_dump()
    assert row.result.pressure == pytest.approx(50.0)
    assert sum(row.result.feed_mole_fractions) == pytest.approx(1.0)


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
    assert len(result.results) == 1
    row = result.results[0]
    assert not isinstance(row, CalculationErrorResultModel), row.model_dump()
    assert row.result.saturation_pressure > 0


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
    assert len(result.results) == 1
    assert result.results[0].status == "success", result.model_dump()


def test_gor_recombination_calculation(
    client_v2: WhitsonPVTClientV2,
    require_id: Callable[[str], int],
    feed_composition,
    surface_process: SurfaceProcessInputModel,
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
    assert len(result.results) == 1
    row = result.results[0]
    assert not isinstance(row, CalculationErrorResultModel), row.model_dump()
    assert sum(row.result.mole_fractions) == pytest.approx(1.0)


def test_separator_process_calculation(
    client_v2: WhitsonPVTClientV2,
    require_id: Callable[[str], int],
    feed_composition,
    surface_process: SurfaceProcessInputModel,
):
    result = client_v2.calculations.calculate_separator_process(
        SeparatorProcessCalculationRequestModel(
            fluid_model_id=require_id("FLUID_MODEL_ID"),
            surface_process=surface_process,
            inputs=[SeparatorProcessCalculationInputModel(feed_composition=feed_composition)],
        )
    )
    assert len(result.results) == 1
    assert result.results[0].status == "success", result.model_dump()


def test_volumetric_to_composition_calculation(
    client_v2: WhitsonPVTClientV2,
    require_id: Callable[[str], int],
    feed_composition,
    surface_process: SurfaceProcessInputModel,
):
    result = client_v2.calculations.calculate_volumetric_to_composition_conversion(
        VolumetricToCompositionConversionCalculationRequestModel(
            fluid_model_id=require_id("FLUID_MODEL_ID"),
            pressure_unit="bara",
            oil_volume_unit="m3",
            gas_volume_unit="m3",
            fluid=VolumetricToCompositionConversionFluidModel(
                bot_oil_composition=feed_composition,
                bot_temperature=50.0,
                bot_temperature_unit="C",
                bot_surface_process=surface_process,
            ),
            inputs=[
                VolumetricToCompositionConversionInputModel(
                    pressure=100.0, oil_volume=1.0, gas_volume=100.0
                )
            ],
        )
    )
    assert len(result.results) == 1
    row = result.results[0]
    assert not isinstance(row, CalculationErrorResultModel), row.model_dump()
    assert len(row.result.mole_numbers) == len(result.component_names)
    assert all(amount >= 0 for amount in row.result.mole_numbers)
    assert sum(row.result.mole_numbers) > 0

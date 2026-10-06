import json
from typing import Any

import pytest

from whitson_pvt_sdk.v2 import WhitsonPVTClientV2
from whitson_pvt_sdk.v2.models import (
    CalculationCompositionEntryModel,
    CalculationErrorResultModel,
    FlashCalculationRequestModel,
    SaturationPressureCalculationRequestModel,
    SurfaceProcessInputModel,
    SurfaceProcessStageInputModel,
    VolumetricToCompositionConversionCalculationRequestModel,
)

OUTPUT_UNITS = {
    "pressure": "bara",
    "temperature": "C",
    "density": "kg/m3",
    "viscosity": "cP",
    "oil_volume": "m3",
    "gas_volume": "Sm3",
    "solution_gas_oil_ratio": "Sm3/m3",
    "solution_oil_gas_ratio": "m3/Sm3",
    "oil_formation_volume_factor": "m3/Sm3",
    "gas_formation_volume_factor": "m3/Sm3",
    "viscosibility": "1/bar",
    "compressibility": "1/bar",
    "thermal_expansion_coefficient": "1/K",
    "bulk_modulus": "bar",
    "molar_enthalpy": "J/mol",
    "specific_enthalpy": "J/kg",
    "molar_entropy": "J/(mol*K)",
    "specific_entropy": "J/(kg*K)",
    "molar_heat_capacity": "J/(mol*K)",
    "specific_heat_capacity": "J/(kg*K)",
    "joule_thomson_coefficient": "K/bar",
    "speed_of_sound": "m/s",
    "thermal_conductivity": "W/(m*K)",
}
FEED = [{"component_name": "C1", "molar_amount": 1.0}]
SURFACE_PROCESS = {
    "pressure_unit": "bara",
    "temperature_unit": "C",
    "stages": [{"pressure": 1.01325, "temperature": 15.0}],
}
ERROR_ROW = {"status": "error", "error": {"code": "calculation_failed", "message": "bad row"}}


def test_volumetric_conversion_serializes_input_and_parses_mixed_rows(transport, httpx_mock):
    payload = {
        "fluid_model_id": 1,
        "pressure_unit": "bara",
        "oil_volume_unit": "m3",
        "gas_volume_unit": "m3",
        "fluid": {
            "bot_oil_composition": FEED,
            "bot_temperature": 80.0,
            "bot_temperature_unit": "C",
            "bot_surface_process": SURFACE_PROCESS,
        },
        "inputs": [
            {"pressure": 100.0, "oil_volume": 0.0, "gas_volume": 1.0},
            {"pressure": 120.0, "oil_volume": 1.0, "gas_volume": 2.0},
        ],
    }
    httpx_mock.add_response(
        method="POST",
        url="https://dev.pvt.whitson.com/external/v2/calculations/volumetric-to-composition-conversion",
        json={
            "component_names": ["C1"],
            "output_unit_system": "SI",
            "output_units": OUTPUT_UNITS,
            "fluid_properties": {
                "oil_saturation_pressure": 100.0,
                "gas_saturation_pressure": 100.0,
                "oil_phase_gas_oil_ratio": 20.0,
                "gas_phase_gas_oil_ratio": None,
            },
            "results": [
                {
                    "status": "success",
                    "result": {"mole_numbers": [0.04], "production_type": "single_phase_gas"},
                },
                ERROR_ROW,
            ],
        },
    )
    result = WhitsonPVTClientV2(
        transport
    ).calculations.calculate_volumetric_to_composition_conversion(
        VolumetricToCompositionConversionCalculationRequestModel.model_validate(payload)
    )
    assert json.loads(httpx_mock.get_requests()[-1].content) == payload
    assert result.fluid_properties.gas_phase_gas_oil_ratio is None
    success, error = result.results
    assert not isinstance(success, CalculationErrorResultModel)
    assert success.result.mole_numbers == [0.04]
    assert isinstance(error, CalculationErrorResultModel)
    assert error.error.message == "bad row"


def test_gor_helper_uses_input_surface_process_without_database_ids(transport, httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://dev.pvt.whitson.com/external/v2/calculations/gor-recombination",
        json={
            "results": [
                {
                    "status": "success",
                    "result": {
                        "component_names": ["C1"],
                        "composition": FEED,
                        "mass_fractions": [1.0],
                        "mole_fractions": [1.0],
                    },
                }
            ]
        },
    )
    feed = [CalculationCompositionEntryModel(component_name="C1", molar_amount=1.0)]
    result = WhitsonPVTClientV2(transport).calculations.get_gor_recombination_feed_composition(
        fluid_model_id=1,
        sample_id=2,
        recombination_gor=100,
        gor_unit="Sm3/m3",
        recombination_type="total_gor",
        feed_composition=feed,
        surface_process=SurfaceProcessInputModel(
            pressure_unit="bara",
            temperature_unit="C",
            stages=[SurfaceProcessStageInputModel(pressure=1.01325, temperature=15.0)],
        ),
    )
    assert result == feed
    assert json.loads(httpx_mock.get_requests()[-1].content)["surface_process"] == SURFACE_PROCESS


@pytest.mark.parametrize("calculation", ["flash", "saturation-pressure"])
def test_extended_phase_properties_and_nullable_values(transport, httpx_mock, calculation):
    phase = {
        "density": 10.0,
        "molecular_weight": 16.0,
        "z_factor": 0.9,
        "split_fraction": 1.0,
        "molar_enthalpy": 20.0,
        "specific_enthalpy": 30.0,
        "molar_entropy": 2.0,
        "specific_entropy": 3.0,
        "viscosity": None,
        "viscosibility": None,
        "isothermal_compressibility": None,
        "thermal_expansion_coefficient": None,
        "isothermal_bulk_modulus": None,
        "isentropic_bulk_modulus": None,
        "molar_isobaric_heat_capacity": None,
        "specific_isobaric_heat_capacity": None,
        "molar_isochoric_heat_capacity": None,
        "specific_isochoric_heat_capacity": None,
        "heat_capacity_ratio": None,
        "joule_thomson_coefficient": None,
        "speed_of_sound": None,
        "thermal_conductivity": None,
    }
    row: dict[str, Any] = {
        "component_names": ["C1"],
        "k_values": [1.0],
        "number_of_phases": 1,
        "temperature": 80.0,
        **{f"{name}_composition": FEED for name in ("feed", "liquid", "vapor")},
        **{f"{name}_mole_fractions": [1.0] for name in ("feed", "liquid", "vapor")},
        **{f"{name}_mole_numbers": [1.0] for name in ("feed", "liquid", "vapor")},
        **{f"{name}_phase_properties": phase for name in ("overall", "liquid", "vapor")},
    }
    if calculation == "flash":
        row["pressure"] = 100.0
    else:
        row.update(saturation_pressure=100.0, saturation_point_type="bubblepoint")
    httpx_mock.add_response(
        method="POST",
        url=f"https://dev.pvt.whitson.com/external/v2/calculations/{calculation}",
        json={
            "output_unit_system": "SI",
            "output_units": OUTPUT_UNITS,
            "results": [{"status": "success", "result": row}, ERROR_ROW],
        },
    )
    client = WhitsonPVTClientV2(transport)
    payload = {
        "fluid_model_id": 1,
        "temperature_unit": "C",
        "inputs": [{"temperature": 80.0, "feed_composition": FEED}],
    }
    if calculation == "flash":
        payload["pressure_unit"] = "bara"
        payload["inputs"][0]["pressure"] = 100.0
        result = client.calculations.calculate_flash(
            FlashCalculationRequestModel.model_validate(payload)
        )
    else:
        result = client.calculations.calculate_saturation_pressure(
            SaturationPressureCalculationRequestModel.model_validate(payload)
        )
    success, error = result.results
    assert not isinstance(success, CalculationErrorResultModel)
    assert success.result.overall_phase_properties.molar_enthalpy == 20.0
    assert success.result.overall_phase_properties.thermal_conductivity is None
    assert isinstance(error, CalculationErrorResultModel)

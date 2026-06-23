import pytest

from whitson_pvt_sdk.shared.models import SampleFlashInput
from whitson_pvt_sdk.v2.resources import Calculations


def make_fluid_model_json(adjusted_compositions):
    return {
        "adjusted_compositions": adjusted_compositions,
        "eos_model": {
            "binary_interaction_parameters": {},
            "boiling_point_temperature_unit": "C",
            "component_properties": [],
            "components_are_mapped": True,
            "critical_molar_volume_for_viscosity_unit": "m3/kmol",
            "critical_molar_volume_unit": "m3/kmol",
            "critical_pressure_unit": "bara",
            "critical_temperature_unit": "C",
            "eos_type": "Peng-Robinson (1977)",
            "id": 1,
            "number_of_components": 2,
            "omega_a": 0.45724,
            "omega_b": 0.0778,
        },
        "gamma_model": {
            "bound": 0.0,
            "first_component": "C7+",
            "id": 1,
            "origin": 0.0,
            "shape": 1.0,
        },
        "id": 123,
        "viscosity_model": {
            "f0": 0.0,
            "id": 1,
            "p0": 0.0,
            "p1": 0.0,
            "p2": 0.0,
            "p3": 0.0,
            "p4": 0.0,
        },
    }


def make_adjusted_composition(composition_id, sample_id, c1_molar_amount, c2_molar_amount):
    return {
        "id": composition_id,
        "sample_id": sample_id,
        "components": [
            {
                "id": composition_id * 2 - 1,
                "molar_composition_id": composition_id,
                "component_name": "C1",
                "molar_amount": c1_molar_amount,
            },
            {
                "id": composition_id * 2,
                "molar_composition_id": composition_id,
                "component_name": "C2",
                "molar_amount": c2_molar_amount,
            },
        ],
    }


def make_flash_response_json():
    return {
        "output_unit_system": "SI",
        "output_units": {
            "density": "kg/m3",
            "gas_formation_volume_factor": "m3/Sm3",
            "gas_volume": "Sm3",
            "oil_formation_volume_factor": "m3/Sm3",
            "oil_volume": "Sm3",
            "pressure": "bara",
            "solution_gas_oil_ratio": "Sm3/Sm3",
            "solution_oil_gas_ratio": "Sm3/Sm3",
            "temperature": "C",
            "viscosity": "cP",
        },
        "results": [
            {
                "status": "error",
                "error": {"code": "calculation_failed", "message": "not relevant"},
            }
        ],
    }


def test_get_sample_feed_compositions_converts_slate_to_slate_response(transport, httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://dev.pvt.whitson.com/external/v2/calculations/sample-to-eos-slate-conversion",
        json={
            "results": [
                {
                    "status": "success",
                    "result": {
                        "component_names": ["C1", "C2"],
                        "mass_fractions": [0.8, 0.2],
                        "mole_fractions": [0.9, 0.1],
                    },
                }
            ]
        },
    )

    result = Calculations(transport).get_sample_feed_compositions(
        fluid_model_id=123,
        sample_ids=[456],
    )

    assert [[entry.model_dump() for entry in composition] for composition in result] == [
        [
            {"component_name": "C1", "molar_amount": 0.9},
            {"component_name": "C2", "molar_amount": 0.1},
        ]
    ]


def test_get_sample_feed_compositions_raises_on_conversion_error(transport, httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://dev.pvt.whitson.com/external/v2/calculations/sample-to-eos-slate-conversion",
        json={
            "results": [
                {
                    "status": "error",
                    "error": {"code": "calculation_failed", "message": "bad sample"},
                }
            ]
        },
    )

    with pytest.raises(ValueError, match="Sample 456 conversion failed: bad sample"):
        Calculations(transport).get_sample_feed_compositions(
            fluid_model_id=123,
            sample_ids=[456],
        )


def test_get_sample_feed_compositions_converts_adjusted_compositions_in_sample_order(
    transport, httpx_mock
):
    httpx_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/fluid-models/123",
        json=make_fluid_model_json(
            [
                make_adjusted_composition(1, 456, 0.9, 0.1),
                make_adjusted_composition(2, 789, 0.7, 0.3),
            ]
        ),
    )

    result = Calculations(transport).get_sample_feed_compositions(
        fluid_model_id=123,
        sample_ids=[789, 456],
        source="adjusted_compositions",
    )

    assert [[entry.model_dump() for entry in composition] for composition in result] == [
        [
            {"component_name": "C1", "molar_amount": 0.7},
            {"component_name": "C2", "molar_amount": 0.3},
        ],
        [
            {"component_name": "C1", "molar_amount": 0.9},
            {"component_name": "C2", "molar_amount": 0.1},
        ],
    ]


def test_get_sample_feed_compositions_raises_on_missing_adjusted_composition(
    transport, httpx_mock
):
    httpx_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/fluid-models/123",
        json=make_fluid_model_json([]),
    )

    with pytest.raises(ValueError, match="Missing adjusted compositions for sample ids: 456"):
        Calculations(transport).get_sample_feed_compositions(
            fluid_model_id=123,
            sample_ids=[456],
            source="adjusted_compositions",
        )


def test_calculate_flash_for_samples_builds_flash_request_from_sample_compositions(
    transport, httpx_mock
):
    httpx_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/fluid-models/123",
        json=make_fluid_model_json(
            [
                make_adjusted_composition(1, 456, 0.9, 0.1),
                make_adjusted_composition(2, 789, 0.7, 0.3),
            ]
        ),
    )
    httpx_mock.add_response(
        method="POST",
        url="https://dev.pvt.whitson.com/external/v2/calculations/flash",
        json=make_flash_response_json(),
    )

    result = Calculations(transport).calculate_flash_for_samples(
        fluid_model_id=123,
        inputs=[
            SampleFlashInput(sample_id=789, pressure=200.0, temperature=80.0),
            SampleFlashInput(sample_id=456, pressure=150.0, temperature=75.0),
        ],
        pressure_unit="bara",
        temperature_unit="C",
        source="adjusted_compositions",
    )

    flash_request = httpx_mock.get_requests()[-1]
    assert result.output_unit_system == "SI"
    assert flash_request.read() == (
        b'{"flash_type":"positive","fluid_model_id":123,'
        b'"inputs":[{"feed_composition":[{"component_name":"C1","molar_amount":0.7},'
        b'{"component_name":"C2","molar_amount":0.3}],"pressure":200.0,"temperature":80.0},'
        b'{"feed_composition":[{"component_name":"C1","molar_amount":0.9},'
        b'{"component_name":"C2","molar_amount":0.1}],"pressure":150.0,"temperature":75.0}],'
        b'"output_unit_system":"SI","pressure_unit":"bara","temperature_unit":"C"}'
    )

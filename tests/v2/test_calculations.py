import pytest

from whitson_pvt_sdk.errors import CalculationError
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

    assert {
        sample_id: [entry.model_dump() for entry in composition]
        for sample_id, composition in result.items()
    } == {
        456: [
            {"component_name": "C1", "molar_amount": 0.9},
            {"component_name": "C2", "molar_amount": 0.1},
        ]
    }


def test_get_sample_feed_composition_returns_single_sample_composition(transport, httpx_mock):
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

    result = Calculations(transport).get_sample_feed_composition(
        fluid_model_id=123,
        sample_id=456,
    )

    assert [entry.model_dump() for entry in result] == [
        {"component_name": "C1", "molar_amount": 0.9},
        {"component_name": "C2", "molar_amount": 0.1},
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

    with pytest.raises(CalculationError, match="bad sample") as exc:
        Calculations(transport).get_sample_feed_compositions(
            fluid_model_id=123,
            sample_ids=[456],
        )
    assert exc.value.code == "calculation_failed"
    assert exc.value.sample_id == 456
    assert exc.value.input_index == 0
    assert exc.value.error is not None


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

    assert {
        sample_id: [entry.model_dump() for entry in composition]
        for sample_id, composition in result.items()
    } == {
        789: [
            {"component_name": "C1", "molar_amount": 0.7},
            {"component_name": "C2", "molar_amount": 0.3},
        ],
        456: [
            {"component_name": "C1", "molar_amount": 0.9},
            {"component_name": "C2", "molar_amount": 0.1},
        ],
    }


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

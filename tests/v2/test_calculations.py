import json

import pytest

from whitson_pvt_sdk.errors import APIError, CalculationError, MissingDataError
from whitson_pvt_sdk.v2.models import (
    CalculationCompositionEntryModel,
    SurfaceProcessInputModel,
    SurfaceProcessStageInputModel,
)
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


def test_get_sample_feed_composition_returns_single_sample_composition(transport, httpx2_mock):
    httpx2_mock.add_response(
        method="POST",
        url="https://dev.pvt.whitson.com/external/v2/calculations/sample-to-eos-slate-conversion",
        json={
            "results": [
                {
                    "status": "success",
                    "result": {
                        "component_names": ["C1", "C2"],
                        "composition": [
                            {"component_name": "C1", "molar_amount": 0.9},
                            {"component_name": "C2", "molar_amount": 0.1},
                        ],
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


def test_get_sample_feed_compositions_raises_on_conversion_error(transport, httpx2_mock):
    httpx2_mock.add_response(
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
    transport, httpx2_mock
):
    httpx2_mock.add_response(
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
    transport, httpx2_mock
):
    httpx2_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/fluid-models/123",
        json=make_fluid_model_json([]),
    )

    with pytest.raises(MissingDataError, match="Missing adjusted compositions for sample ids: 456"):
        Calculations(transport).get_sample_feed_compositions(
            fluid_model_id=123,
            sample_ids=[456],
            source="adjusted_compositions",
        )


def _converted(molar_amount):
    return {
        "status": "success",
        "result": {
            "component_names": ["C1"],
            "composition": [{"component_name": "C1", "molar_amount": molar_amount}],
            "mass_fractions": [1.0],
            "mole_fractions": [1.0],
        },
    }


def test_a_result_count_other_than_the_sample_count_is_a_server_error(transport, httpx2_mock):
    httpx2_mock.add_response(
        method="POST",
        url="https://dev.pvt.whitson.com/external/v2/calculations/sample-to-eos-slate-conversion",
        json={"results": [_converted(1.0)]},
    )

    with pytest.raises(APIError, match="1 result for 2 samples"):
        Calculations(transport).get_sample_feed_compositions(
            fluid_model_id=123, sample_ids=[456, 789]
        )


def test_gor_recombination_source_missing_a_sample_is_refused_before_any_request(
    transport, httpx2_mock
):
    feed = [CalculationCompositionEntryModel(component_name="C1", molar_amount=1.0)]

    with pytest.raises(MissingDataError, match="no feed composition for sample ids: 789"):
        Calculations(transport).get_gor_recombination_feed_compositions(
            fluid_model_id=123,
            gor_values={456: 100.0, 789: 200.0},
            gor_unit="Sm3/m3",
            recombination_type="total_gor",
            surface_process=SurfaceProcessInputModel(
                pressure_unit="bara",
                temperature_unit="C",
                stages=[SurfaceProcessStageInputModel(pressure=1.01325, temperature=15.0)],
            ),
            source={456: feed},
        )

    assert httpx2_mock.get_requests() == []


def test_gor_recombination_uses_the_given_surface_process_and_feed(transport, httpx2_mock):
    feed = [{"component_name": "C1", "molar_amount": 1.0}]
    recombined = [{"component_name": "C1", "molar_amount": 0.7}]
    httpx2_mock.add_response(
        method="POST",
        url="https://dev.pvt.whitson.com/external/v2/calculations/gor-recombination",
        json={
            "results": [
                {
                    "status": "success",
                    "result": {
                        "component_names": ["C1"],
                        "composition": recombined,
                        "mass_fractions": [1.0],
                        "mole_fractions": [1.0],
                    },
                }
            ]
        },
    )

    result = Calculations(transport).get_gor_recombination_feed_composition(
        fluid_model_id=1,
        sample_id=2,
        recombination_gor=100,
        gor_unit="Sm3/m3",
        recombination_type="total_gor",
        source=[CalculationCompositionEntryModel.model_validate(entry) for entry in feed],
        surface_process=SurfaceProcessInputModel(
            pressure_unit="bara",
            temperature_unit="C",
            stages=[SurfaceProcessStageInputModel(pressure=1.01325, temperature=15.0)],
        ),
    )

    assert [entry.model_dump() for entry in result] == recombined
    sent = json.loads(httpx2_mock.get_requests()[-1].content)
    assert [entry["feed_composition"] for entry in sent["inputs"]] == [feed]
    assert sent["surface_process"] == {
        "pressure_unit": "bara",
        "temperature_unit": "C",
        "stages": [{"pressure": 1.01325, "temperature": 15.0}],
    }

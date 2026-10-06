import json

import pytest

from whitson_pvt_sdk.v2.models import CreateSampleModel, GetSampleListModel, UpdateSampleModel
from whitson_pvt_sdk.v2.resources import Samples


def make_sample_json(**kwargs):
    return {"id": kwargs.pop("id", 1), "name": kwargs.pop("name", "Sample"), **kwargs}


def test_list_samples_returns_sample_list_model(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/wells/1",
        json={"samples": [make_sample_json(name="S1"), make_sample_json(id=2, name="S2")]},
    )

    result = Samples(transport).list(1)

    assert isinstance(result, GetSampleListModel)
    assert len(result.samples) == 2


@pytest.mark.parametrize("method", ["create", "update"])
def test_new_sample_fields_and_experiment_types_round_trip(transport, httpx_mock, method):
    payload = {
        "name": "SSF sample",
        "well_id": 1,
        "type": "SEP",
        "fluid_type": "Oil",
        "primary_recombination_type": "ssf",
        "ssf_recombined_fluid_gor": 50.0,
        "ssf_recombined_fluid_gor_unit": "Sm3/m3",
        "ssf_flashed_oil_density": 0.8,
        "ssf_flashed_oil_density_unit": "g/cm3",
        "ssf_flashed_gas_specific_gravity": 0.7,
        "experiments": [
            {
                "type": "MultiContact",
                "name": "Contact",
                "direction": "Forward Contact",
                "temperature": 80.0,
                "temperature_unit": "C",
                "pressure": 100.0,
                "pressure_unit": "bara",
                "stages": [{"viscosity_oil": 1.2}],
            },
            {
                "type": "VISCO",
                "name": "Viscosity",
                "temperature": 80.0,
                "temperature_unit": "C",
                "saturation_pressure_type": "Bubblepoint",
                "stages": [
                    {
                        "pressure": 100.0,
                        "oil_density": 0.8,
                        "gas_density": 0.1,
                        "is_saturation_pressure": True,
                    }
                ],
            },
            {
                "type": "SwellTest",
                "name": "Swell",
                "temperature": 80.0,
                "temperature_unit": "C",
                "stage_data": [
                    {
                        "moles_injected": 10.0,
                        "saturation_pressure": 100.0,
                        "single_phase_viscosity_unit": "cP",
                        "cce_data": [{"pressure": 150.0, "single_phase_viscosity": 0.5}],
                    }
                ],
            },
        ],
    }
    httpx_mock.add_response(
        method="POST" if method == "create" else "PUT",
        url="https://dev.pvt.whitson.com/external/v2/samples"
        + ("" if method == "create" else "/1"),
        json={"id": 1, **payload},
    )
    samples = Samples(transport)
    if method == "create":
        result = samples.create(CreateSampleModel.model_validate(payload))
    else:
        result = samples.update(1, UpdateSampleModel.model_validate(payload))
    assert json.loads(httpx_mock.get_requests()[-1].content) == payload
    dumped = result.model_dump(exclude_unset=True)
    for name, value in payload.items():
        assert dumped[name] == value

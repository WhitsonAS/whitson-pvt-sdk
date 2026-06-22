from whitson_pvt_sdk.v1.models import (
    CreateSampleListModel,
    CreateSampleModel,
    GetSampleListModel,
    GetSampleModel,
    UpdateSampleListModel,
    UpdateSampleModel,
)
from whitson_pvt_sdk.v1.resources import Samples


def make_sample_json(**kwargs):
    return {"id": kwargs.pop("id", 1), "name": kwargs.pop("name", "Sample"), **kwargs}


def test_list_samples_returns_sample_list_model(transport_v1, httpx_mock):
    httpx_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v1/wells/1",
        json={"samples": [make_sample_json(name="S1"), make_sample_json(id=2, name="S2")]},
    )
    result = Samples(transport_v1).list(1)
    assert isinstance(result, GetSampleListModel)
    assert len(result.samples) == 2


def test_get_sample_returns_get_sample_model(transport_v1, httpx_mock):
    httpx_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v1/samples/42",
        json=make_sample_json(id=42),
    )
    result = Samples(transport_v1).get(42)
    assert isinstance(result, GetSampleModel)
    assert result.id == 42


def test_create_sample_excludes_unset_fields(transport_v1, httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://dev.pvt.whitson.com/external/v1/samples",
        json=make_sample_json(name="New Sample"),
    )
    data = CreateSampleModel(name="New Sample", fluid_type="Oil", type="REC", well_id=1)
    result = Samples(transport_v1).create(data)
    assert result.name == "New Sample"


def test_create_samples_bulk_serializes_as_list(transport_v1, httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://dev.pvt.whitson.com/external/v1/samples/bulk",
        json={"samples": [make_sample_json(id=1), make_sample_json(id=2)]},
    )
    data = CreateSampleListModel.model_validate(
        [
            {"name": "S1", "fluid_type": "Oil", "type": "REC", "well_id": 1},
            {"name": "S2", "fluid_type": "Oil", "type": "REC", "well_id": 1},
        ]
    )
    result = Samples(transport_v1).create_bulk(data)
    assert isinstance(result, GetSampleListModel)
    assert len(result.samples) == 2

    body = httpx_mock.get_requests()[-1].read().decode()
    assert "S1" in body
    assert "S2" in body


def test_update_sample_excludes_unset_fields(transport_v1, httpx_mock):
    httpx_mock.add_response(
        method="PUT",
        url="https://dev.pvt.whitson.com/external/v1/samples/1",
        json=make_sample_json(id=1, name="Updated"),
    )
    data = UpdateSampleModel(name="Updated")
    result = Samples(transport_v1).update(1, data)
    assert result.name == "Updated"


def test_update_samples_bulk_serializes_as_list(transport_v1, httpx_mock):
    httpx_mock.add_response(
        method="PUT",
        url="https://dev.pvt.whitson.com/external/v1/samples/bulk",
        json={"samples": [make_sample_json(id=1)]},
    )
    data = UpdateSampleListModel.model_validate([{"id": 1, "name": "U1"}])
    result = Samples(transport_v1).update_bulk(data)
    assert isinstance(result, GetSampleListModel)

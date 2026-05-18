from whitson_pvt_sdk.models.v1._generated import (
    CreateWellModel,
    GetWellModel,
    UpdateWellModel,
    UpdateWellsListModel,
    WellsListModel,
)
from whitson_pvt_sdk.v1.resources import Wells


def make_well_json(name="Test Well", **kwargs):
    return {
        "id": kwargs.pop("id", 1),
        "name": name,
        "basin_name": None,
        "field_name": None,
        "field_segment_name": None,
        "formation_name": None,
        "formation_zone_name": None,
        "sub_basin_name": None,
        "samples": [],
        **kwargs,
    }


def test_list_wells_returns_wells_list_model(transport_v1, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v1/regions/1/wells",
        json={"wells": [make_well_json(name="W1"), make_well_json(id=2, name="W2")]},
    )
    result = Wells(transport_v1).list(1)
    assert isinstance(result, WellsListModel)
    assert len(result.wells) == 2


def test_get_well_returns_get_well_model(transport_v1, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v1/wells/42",
        json=make_well_json(id=42),
    )
    result = Wells(transport_v1).get(42)
    assert isinstance(result, GetWellModel)
    assert result.id == 42


def test_create_well_excludes_samples_field(transport_v1, httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://pvt.whitson.com/external/v1/wells",
        json=make_well_json(name="New Well"),
    )
    data = CreateWellModel(name="New Well", region_id=1)
    Wells(transport_v1).create(data)

    body = httpx_mock.get_requests()[-1].read().decode()
    assert '"name"' in body
    assert '"region_id"' in body
    assert '"samples"' not in body


def test_update_well_excludes_unset_fields(transport_v1, httpx_mock):
    httpx_mock.add_response(
        method="PUT",
        url="https://pvt.whitson.com/external/v1/wells/1",
        json=make_well_json(id=1, name="Renamed"),
    )
    data = UpdateWellModel(name="Renamed")
    result = Wells(transport_v1).update(1, data)
    assert result.name == "Renamed"


def test_update_wells_bulk_serializes_as_list(transport_v1, httpx_mock):
    httpx_mock.add_response(
        method="PUT",
        url="https://pvt.whitson.com/external/v1/wells/bulk",
        json={"wells": [make_well_json(id=1), make_well_json(id=2)]},
    )
    data = UpdateWellsListModel.model_validate(
        {"root": [{"id": 1, "name": "W1"}, {"id": 2, "name": "W2"}]}
    )
    result = Wells(transport_v1).update_bulk(data)
    assert isinstance(result, WellsListModel)
    assert len(result.wells) == 2

    body = httpx_mock.get_requests()[-1].read().decode()
    assert '"name"' in body
    assert '"samples"' not in body

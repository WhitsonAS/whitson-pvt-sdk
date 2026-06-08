from whitson_pvt_sdk.v1.models import (
    CreateRegionModel,
    GetRegionModel,
    RegionsListModel,
    UpdateRegionModel,
)
from whitson_pvt_sdk.v1.resources import Regions


def make_region_json(name="Test Region", **kwargs):
    return {"id": kwargs.pop("id", 1), "name": name, **kwargs}


def test_list_regions_returns_regions_list_model(transport_v1, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v1/regions",
        json={"regions": [make_region_json(name="R1"), make_region_json(id=2, name="R2")]},
    )
    result = Regions(transport_v1).list()
    assert isinstance(result, RegionsListModel)
    assert len(result.regions) == 2
    assert result.regions[0].name == "R1"
    assert result.regions[1].name == "R2"


def test_get_region_returns_get_region_model(transport_v1, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v1/regions/42",
        json=make_region_json(id=42, name="My Region"),
    )
    result = Regions(transport_v1).get(42)
    assert isinstance(result, GetRegionModel)
    assert result.id == 42
    assert result.name == "My Region"


def test_create_region_excludes_unset_fields(transport_v1, httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://pvt.whitson.com/external/v1/regions",
        json=make_region_json(name="New Region"),
    )
    data = CreateRegionModel(
        name="New Region", region_type="single_field", reservoir_type="Conventional"
    )
    result = Regions(transport_v1).create(data)
    assert result.name == "New Region"

    body = httpx_mock.get_requests()[-1].read().decode()
    assert '"name"' in body
    assert '"id"' not in body
    assert '"note"' not in body


def test_update_region_excludes_unset_fields(transport_v1, httpx_mock):
    httpx_mock.add_response(
        method="PUT",
        url="https://pvt.whitson.com/external/v1/regions/1",
        json=make_region_json(id=1, name="Renamed"),
    )
    data = UpdateRegionModel(name="Renamed")
    result = Regions(transport_v1).update(1, data)
    assert result.name == "Renamed"

    body = httpx_mock.get_requests()[-1].read().decode()
    assert '"name"' in body
    assert '"id"' not in body

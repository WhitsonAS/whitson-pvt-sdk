from whitson_pvt_sdk.models.v2._generated import (
    CreateRegionModel,
    PaginatedRegionsModel,
    UpdateRegionModel,
)
from whitson_pvt_sdk.v2.resources import Regions


def make_region_json(name="Test Region", **kwargs):
    return {"id": kwargs.pop("id", 1), "name": name, **kwargs}


def test_list_regions_returns_paginated_model(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/regions",
        json={
            "regions": [make_region_json(name="R1")],
            "pagination": {"next_cursor": "nxt", "prev_cursor": None},
        },
    )
    result = Regions(transport).list()
    assert isinstance(result, PaginatedRegionsModel)
    assert len(result.regions) == 1
    assert result.pagination.next_cursor == "nxt"
    assert result.pagination.prev_cursor is None


def test_list_regions_pagination_with_both_cursors(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/regions",
        json={
            "regions": [],
            "pagination": {"next_cursor": "nxt", "prev_cursor": "prv"},
        },
    )
    result = Regions(transport).list()
    assert result.pagination.next_cursor == "nxt"
    assert result.pagination.prev_cursor == "prv"


def test_list_regions_passes_cursor(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/regions?cursor=nxt&limit=25",
        json={
            "regions": [],
            "pagination": {"next_cursor": None, "prev_cursor": "prv"},
        },
    )
    result = Regions(transport).list(cursor="nxt", limit=25)
    assert result.pagination.prev_cursor == "prv"


def test_get_region_v2(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/regions/1",
        json=make_region_json(),
    )
    result = Regions(transport).get(1)
    assert result.id == 1


def test_create_region_v2_excludes_unset(transport, httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://pvt.whitson.com/external/v2/regions",
        json=make_region_json(name="New"),
    )
    result = Regions(transport).create(
        CreateRegionModel(name="New", region_type="single_field", reservoir_type="Conventional")
    )
    assert result.name == "New"

    body = httpx_mock.get_requests()[-1].read().decode()
    assert '"name"' in body
    assert '"id"' not in body


def test_update_region_v2_excludes_unset(transport, httpx_mock):
    httpx_mock.add_response(
        method="PUT",
        url="https://pvt.whitson.com/external/v2/regions/1",
        json=make_region_json(id=1, name="Updated"),
    )
    result = Regions(transport).update(1, UpdateRegionModel(name="Updated"))
    assert result.name == "Updated"

from whitson_pvt_sdk.v2.models import PaginatedWellsModel
from whitson_pvt_sdk.v2.resources import BlackOilTables, Regions, Wells


def _pagination_json(collection_name: str) -> dict:
    return {
        collection_name: [],
        "pagination": {"next_cursor": None, "prev_cursor": "prv"},
    }


def test_list_wells_passes_cursor(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/regions/1/wells?cursor=nxt&limit=25",
        json=_pagination_json("wells"),
    )
    result = Wells(transport).list(region_id=1, cursor="nxt", limit=25)
    assert isinstance(result, PaginatedWellsModel)
    assert result.pagination.prev_cursor == "prv"


def test_list_black_oil_tables_passes_cursor(transport, httpx_mock):
    httpx_mock.add_response(
        url=(
            "https://dev.pvt.whitson.com/external/v2/"
            "fluid-models/3/black-oil-tables?cursor=nxt&limit=25"
        ),
        json=_pagination_json("black_oil_tables"),
    )
    result = BlackOilTables(transport).list(fluid_model_id=3, cursor="nxt", limit=25)
    assert result.pagination.prev_cursor == "prv"


def test_regions_list_all_walks_all_pages(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/regions?limit=25",
        json={
            "regions": [],
            "pagination": {"next_cursor": "nxt", "prev_cursor": None},
        },
    )
    httpx_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/regions?cursor=nxt&limit=25",
        json={
            "regions": [],
            "pagination": {"next_cursor": None, "prev_cursor": "prv"},
        },
    )

    assert Regions(transport).list_all(limit=25) == []
    get_requests = [request for request in httpx_mock.get_requests() if request.method == "GET"]
    assert len(get_requests) == 2

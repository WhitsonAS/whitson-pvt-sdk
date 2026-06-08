from whitson_pvt_sdk.v2.models import PaginatedWellsModel
from whitson_pvt_sdk.v2.resources import BlackOilTables, FluidModels, Projects, Wells


def _pagination_json(collection_name: str) -> dict:
    return {
        collection_name: [],
        "pagination": {"next_cursor": None, "prev_cursor": "prv"},
    }


def test_list_projects_passes_cursor(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/regions/1/projects?cursor=nxt&limit=25",
        json=_pagination_json("projects"),
    )
    result = Projects(transport).list(region_id=1, cursor="nxt", limit=25)
    assert result.pagination.prev_cursor == "prv"


def test_list_wells_passes_cursor(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/regions/1/wells?cursor=nxt&limit=25",
        json=_pagination_json("wells"),
    )
    result = Wells(transport).list(region_id=1, cursor="nxt", limit=25)
    assert isinstance(result, PaginatedWellsModel)
    assert result.pagination.prev_cursor == "prv"


def test_list_fluid_models_passes_cursor(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/projects/2/fluid-models?cursor=nxt&limit=25",
        json=_pagination_json("fluid_models"),
    )
    result = FluidModels(transport).list(project_id=2, cursor="nxt", limit=25)
    assert result.pagination.prev_cursor == "prv"


def test_list_black_oil_tables_passes_cursor(transport, httpx_mock):
    httpx_mock.add_response(
        url=(
            "https://pvt.whitson.com/external/v2/"
            "fluid-models/3/black-oil-tables?cursor=nxt&limit=25"
        ),
        json=_pagination_json("black_oil_tables"),
    )
    result = BlackOilTables(transport).list(fluid_model_id=3, cursor="nxt", limit=25)
    assert result.pagination.prev_cursor == "prv"

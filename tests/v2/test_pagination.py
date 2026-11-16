import pytest


@pytest.mark.parametrize(
    "resource,path,args",
    [
        ("regions", "/regions", {}),
        ("wells", "/regions/1/wells", {"region_id": 1}),
        ("projects", "/regions/1/projects", {"region_id": 1}),
        ("fluid_models", "/projects/1/fluid-models", {"project_id": 1}),
        ("black_oil_tables", "/fluid-models/1/black-oil-tables", {"fluid_model_id": 1}),
    ],
)
@pytest.mark.parametrize("method", ["list", "iterate", "list_all"])
def test_name_filter_is_sent_on_every_page(client, httpx2_mock, resource, path, args, method):
    url = f"https://dev.pvt.whitson.com/external/v2{path}"
    pages = 1 if method == "list" else 2
    for index in range(pages):
        query = "limit=2&name=Exact+name"
        if index:
            query += "&cursor=next"
        httpx2_mock.add_response(
            method="GET",
            url=f"{url}?{query}",
            json={
                resource: [],
                "pagination": {
                    "next_cursor": "next" if index == 0 and pages == 2 else None,
                    "prev_cursor": None,
                },
            },
        )
    facade = getattr(client, resource)
    result = getattr(facade, method)(**args, name="Exact name", limit=2)
    if method != "list":
        assert list(result) == []
    assert len([req for req in httpx2_mock.get_requests() if req.method == "GET"]) == pages

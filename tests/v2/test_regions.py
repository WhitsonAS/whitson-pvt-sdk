import json

from whitson_pvt_sdk.v2.models import CreateRegionModel
from whitson_pvt_sdk.v2.resources import Regions


def test_create_region_sends_only_the_fields_set(transport, httpx2_mock):
    httpx2_mock.add_response(
        method="POST",
        url="https://dev.pvt.whitson.com/external/v2/regions",
        json={"id": 1, "name": "New"},
    )

    result = Regions(transport).create(
        CreateRegionModel(name="New", region_type="single_field", reservoir_type="Conventional")
    )

    assert result.name == "New"
    assert json.loads(httpx2_mock.get_requests()[-1].content) == {
        "name": "New",
        "region_type": "single_field",
        "reservoir_type": "Conventional",
    }

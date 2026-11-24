import json

from tests.conftest import NAMELESS_WELL
from whitson_pvt_sdk.v2.models import CreateWellModel, CreateWellSampleModel
from whitson_pvt_sdk.v2.resources import Wells

SAMPLE = {"name": "S1", "type": "SEP", "fluid_type": "Oil"}


def test_create_well_leaves_its_samples_out_of_the_request(transport, httpx2_mock):
    httpx2_mock.add_response(
        method="POST",
        url="https://dev.pvt.whitson.com/external/v2/wells",
        json={**NAMELESS_WELL, "id": 4, "samples": []},
    )

    result = Wells(transport).create(
        CreateWellModel(
            name="W1", region_id=3, samples=[CreateWellSampleModel.model_validate(SAMPLE)]
        )
    )

    assert result.id == 4
    assert json.loads(httpx2_mock.get_requests()[-1].content) == {"name": "W1", "region_id": 3}

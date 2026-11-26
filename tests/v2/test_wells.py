import json

import pytest
from pydantic import ValidationError

from tests.conftest import NAMELESS_WELL
from whitson_pvt_sdk.v2.models import (
    CreateWellModel,
    CreateWellSampleModel,
    GetWellModel,
    UpdateWellModel,
    UpdateWellsListModel,
    WellIdListModel,
    WellIdModel,
    WellsListModel,
)
from whitson_pvt_sdk.v2.resources import Wells

SAMPLE = {"name": "S1", "type": "SEP", "fluid_type": "Oil"}
WELL_URL = "https://dev.pvt.whitson.com/external/v2/wells/4"
BULK_URL = "https://dev.pvt.whitson.com/external/v2/wells/bulk"
FULL_WELL = {**NAMELESS_WELL, "id": 4, "name": "W1"}
WELL_MISSING_A_FIELD = {key: value for key, value in FULL_WELL.items() if key != "basin_name"}
BULK_UPDATE = UpdateWellsListModel.model_validate([{"id": 4, "name": "W1"}])


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


@pytest.mark.parametrize(
    ("well", "expected"),
    [(FULL_WELL, GetWellModel.model_validate(FULL_WELL)), ({"id": 4}, WellIdModel(id=4))],
    ids=["with-wells-read", "without-wells-read"],
)
def test_update_well_answers_with_the_shape_the_token_may_read(
    transport, httpx2_mock, well, expected
):
    httpx2_mock.add_response(method="PUT", url=WELL_URL, json=well)

    result = Wells(transport).update(4, UpdateWellModel(name="W1"))

    assert type(result) is type(expected)
    assert result == expected


@pytest.mark.parametrize(
    ("wells", "expected"),
    [
        ([FULL_WELL], WellsListModel.model_validate({"wells": [FULL_WELL]})),
        ([{"id": 4}], WellIdListModel(wells=[WellIdModel(id=4)])),
    ],
    ids=["with-wells-read", "without-wells-read"],
)
def test_update_wells_answers_with_the_shape_the_token_may_read(
    transport, httpx2_mock, wells, expected
):
    httpx2_mock.add_response(method="PUT", url=BULK_URL, json={"wells": wells})

    result = Wells(transport).update_bulk(BULK_UPDATE)

    assert type(result) is type(expected)
    assert result == expected


def test_update_wells_refuses_a_full_well_missing_a_field_instead_of_keeping_only_its_id(
    transport, httpx2_mock
):
    httpx2_mock.add_response(method="PUT", url=WELL_URL, json=WELL_MISSING_A_FIELD)
    httpx2_mock.add_response(
        method="PUT", url=BULK_URL, json={"wells": [FULL_WELL, WELL_MISSING_A_FIELD]}
    )

    with pytest.raises(ValidationError):
        Wells(transport).update(4, UpdateWellModel(name="W1"))
    with pytest.raises(ValidationError):
        Wells(transport).update_bulk(BULK_UPDATE)

from collections.abc import Callable

import pytest
from pydantic import BaseModel, ValidationError

from tests.conftest import NAMELESS_WELL
from whitson_pvt_sdk.http import HTTPTransport
from whitson_pvt_sdk.v2.models import (
    GetRegionModel,
    GetSampleListModel,
    GetSampleModel,
    GetWellModel,
    RegionIdModel,
    SampleIdListModel,
    SampleIdModel,
    UpdateRegionModel,
    UpdateSampleListModel,
    UpdateSampleModel,
    UpdateWellModel,
    UpdateWellsListModel,
    WellIdListModel,
    WellIdModel,
    WellsListModel,
)
from whitson_pvt_sdk.v2.resources import Regions, Samples, Wells

API = "https://dev.pvt.whitson.com/external/v2"
FULL_REGION = {
    "id": 1,
    "name": "R1",
    "region_type": "single_field",
    "reservoir_type": "Conventional",
    "public": False,
    "note": "",
}
FULL_SAMPLE = {
    "id": 2,
    "well_id": 4,
    "name": "S1",
    "type": "SEP",
    "fluid_type": "Oil",
    "note": None,
    "experiments": [],
    "reservoir_pressure": None,
    "reservoir_temperature": None,
}
FULL_WELL = {**NAMELESS_WELL, "id": 4, "name": "W1"}
WELL_MISSING_A_FIELD = {key: value for key, value in FULL_WELL.items() if key != "basin_name"}

Update = Callable[[HTTPTransport], BaseModel]
UPDATES: dict[str, tuple[str, Update]] = {
    "region": (
        f"{API}/regions/1",
        lambda transport: Regions(transport).update(1, UpdateRegionModel(note="n")),
    ),
    "sample": (
        f"{API}/samples/2",
        lambda transport: Samples(transport).update(2, UpdateSampleModel(note="n")),
    ),
    "samples": (
        f"{API}/samples/bulk",
        lambda transport: Samples(transport).update_bulk(
            UpdateSampleListModel.model_validate([{"id": 2, "note": "n"}])
        ),
    ),
    "well": (
        f"{API}/wells/4",
        lambda transport: Wells(transport).update(4, UpdateWellModel(name="W1")),
    ),
    "wells": (
        f"{API}/wells/bulk",
        lambda transport: Wells(transport).update_bulk(
            UpdateWellsListModel.model_validate([{"id": 4, "name": "W1"}])
        ),
    ),
}


@pytest.mark.parametrize(
    ("update", "answer", "expected"),
    [
        ("region", FULL_REGION, GetRegionModel),
        ("region", {"id": 1}, RegionIdModel),
        ("sample", FULL_SAMPLE, GetSampleModel),
        ("sample", {"id": 2}, SampleIdModel),
        ("samples", {"samples": [FULL_SAMPLE]}, GetSampleListModel),
        ("samples", {"samples": [{"id": 2}]}, SampleIdListModel),
        ("well", FULL_WELL, GetWellModel),
        ("well", {"id": 4}, WellIdModel),
        ("wells", {"wells": [FULL_WELL]}, WellsListModel),
        ("wells", {"wells": [{"id": 4}]}, WellIdListModel),
    ],
    ids=lambda value: value.__name__ if isinstance(value, type) else None,
)
def test_update_answers_with_the_shape_the_token_may_read(
    transport, httpx2_mock, update, answer, expected
):
    url, call = UPDATES[update]
    httpx2_mock.add_response(method="PUT", url=url, json=answer)

    result = call(transport)

    assert type(result) is expected
    assert result == expected.model_validate(answer)


@pytest.mark.parametrize(
    ("update", "answer"),
    [
        ("region", {**FULL_REGION, "region_type": "unknown"}),
        ("sample", {**FULL_SAMPLE, "type": "unknown"}),
        ("samples", {"samples": [FULL_SAMPLE, {**FULL_SAMPLE, "type": "unknown"}]}),
        ("well", WELL_MISSING_A_FIELD),
        ("wells", {"wells": [FULL_WELL, WELL_MISSING_A_FIELD]}),
        ("wells", {"wells": [{"id": 4}, FULL_WELL]}),
    ],
    ids=["region", "sample", "samples", "well", "wells", "wells-mixed"],
)
def test_update_refuses_a_full_answer_with_a_bad_field_instead_of_keeping_only_its_id(
    transport, httpx2_mock, update, answer
):
    url, call = UPDATES[update]
    httpx2_mock.add_response(method="PUT", url=url, json=answer)

    with pytest.raises(ValidationError):
        call(transport)

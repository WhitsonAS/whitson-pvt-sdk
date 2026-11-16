import pytest

from whitson_pvt_sdk.errors import AuthError
from whitson_pvt_sdk.v2.models import GetSampleListModel
from whitson_pvt_sdk.v2.resources import Samples


def make_sample_json(**kwargs):
    return {"id": kwargs.pop("id", 1), "name": kwargs.pop("name", "Sample"), **kwargs}


WELL = {
    "id": 1,
    **{
        f"{name}_name": None
        for name in ("basin", "field", "field_segment", "formation", "formation_zone", "sub_basin")
    },
}


def test_list_samples_returns_sample_list_model(transport, httpx2_mock):
    httpx2_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/wells/1",
        json={**WELL, "samples": [make_sample_json(name="S1"), make_sample_json(id=2, name="S2")]},
    )

    result = Samples(transport).list(1)

    assert isinstance(result, GetSampleListModel)
    assert len(result.samples) == 2


def test_list_samples_refuses_a_well_returned_without_its_samples(transport, httpx2_mock):
    httpx2_mock.add_response(url="https://dev.pvt.whitson.com/external/v2/wells/1", json=WELL)

    with pytest.raises(AuthError, match="samples:read"):
        Samples(transport).list(1)

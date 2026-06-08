from whitson_pvt_sdk.v2.models import GetSampleListModel
from whitson_pvt_sdk.v2.resources import Samples


def make_sample_json(**kwargs):
    return {"id": kwargs.pop("id", 1), "name": kwargs.pop("name", "Sample"), **kwargs}


def test_list_samples_returns_sample_list_model(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/wells/1",
        json={"samples": [make_sample_json(name="S1"), make_sample_json(id=2, name="S2")]},
    )

    result = Samples(transport).list(1)

    assert isinstance(result, GetSampleListModel)
    assert len(result.samples) == 2

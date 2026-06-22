from whitson_pvt_sdk.v1.models import ImportCommitResultModel
from whitson_pvt_sdk.v1.resources import Reports


def test_import_archive_v1_compatibility(transport_v1, httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://dev.pvt.whitson.com/external/v1/reports/import",
        json={"created": {"regions": 1}, "id_map": {}, "reused": {}, "skipped": {}},
    )
    result = Reports(transport_v1).import_archive(b"archive")
    assert isinstance(result, ImportCommitResultModel)
    assert result.created == {"regions": 1}

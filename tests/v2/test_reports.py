from whitson_pvt_sdk.models.manual import ExternalImportArchiveOptions
from whitson_pvt_sdk.models.v2._generated import ImportCommitResultModel, ImportPreflightResultModel
from whitson_pvt_sdk.v2.resources import Reports


def test_export_report_v2(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://pvt.whitson.com/external/v2/reports/1/export",
        content=b"data",
    )
    data, filename = Reports(transport).export(1)
    assert data == b"data"
    assert filename == "report_1_export.zip"


def test_preflight_import_v2_model(transport, httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://pvt.whitson.com/external/v2/reports/import/preflight",
        json={
            "can_commit": True,
            "collisions": [],
            "skipped": {},
            "suggestions": [],
            "summary": {},
        },
    )
    result = Reports(transport).preflight_import(b"archive")
    assert isinstance(result, ImportPreflightResultModel)


def test_preflight_import_v2_sends_meta_data_json(transport, httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://pvt.whitson.com/external/v2/reports/import/preflight",
        json={
            "can_commit": True,
            "collisions": [],
            "skipped": {},
            "suggestions": [],
            "summary": {},
        },
    )
    Reports(transport).preflight_import(
        b"archive",
        ExternalImportArchiveOptions(region_id=42, acknowledge_suggestions=True),
    )
    body = httpx_mock.get_requests()[-1].read().decode()
    assert "archive.zip" in body
    assert "meta_data" in body
    assert '"region_id":42' in body
    assert '"acknowledge_suggestions":true' in body


def test_import_archive_v2(transport, httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://pvt.whitson.com/external/v2/reports/import",
        json={"created": {"regions": 1}, "id_map": {}, "reused": {}, "skipped": {}},
    )
    result = Reports(transport).import_archive(b"archive")
    assert isinstance(result, ImportCommitResultModel)

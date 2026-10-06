from whitson_pvt_sdk.shared.models import ImportArchiveOptions
from whitson_pvt_sdk.v2.models import ReportArchiveCommitResultModel
from whitson_pvt_sdk.v2.resources import Reports


def test_export_report_v2(transport, httpx_mock):
    httpx_mock.add_response(
        url="https://dev.pvt.whitson.com/external/v2/reports/1/export",
        content=b"data",
    )
    data, filename = Reports(transport).export(1)
    assert data == b"data"
    assert filename == "report_1_export.zip"


def test_preflight_import_v2_sends_meta_data_json(transport, httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://dev.pvt.whitson.com/external/v2/reports/import/preflight",
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
        ImportArchiveOptions(region_id=42, acknowledge_suggestions=True),
    )
    body = httpx_mock.get_requests()[-1].read().decode()
    assert "archive.zip" in body
    assert "meta_data" in body
    assert '"region_id":42' in body
    assert '"acknowledge_suggestions":true' in body


def test_export_osdu_passes_options_and_explicit_false(transport, httpx_mock):
    httpx_mock.add_response(
        url=(
            "https://dev.pvt.whitson.com/external/v2/reports/1/export"
            "?format=osdu&include_whitson_native_payload=true&include_structured_experiments=false"
        ),
        content=b"osdu-archive",
    )
    data, _ = Reports(transport).export(
        1, format="osdu", include_whitson_native_payload=True, include_structured_experiments=False
    )
    assert data == b"osdu-archive"


def test_archive_import_returns_archive_result_not_session_result(transport, httpx_mock):
    payload = {"created": {"samples": 1}, "id_map": {}, "reused": {}, "skipped": {}}
    httpx_mock.add_response(
        method="POST",
        url="https://dev.pvt.whitson.com/external/v2/reports/import",
        status_code=201,
        json=payload,
    )
    result = Reports(transport).import_archive(b"archive")
    assert isinstance(result, ReportArchiveCommitResultModel)
    assert result.model_dump() == payload

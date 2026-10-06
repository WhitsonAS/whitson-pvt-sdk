import json

import pytest

from whitson_pvt_sdk.errors import APIError
from whitson_pvt_sdk.v2 import WhitsonPVTClientV2
from whitson_pvt_sdk.v2.models import (
    ImportCommitRequestModel,
    ImportCommitResultModel,
    ImportRecordResolutionModel,
    ImportSessionCreateOptionsModel,
    ImportSessionModel,
    OSDURecordEnvelopeModel,
    SingleRecordImportRequestModel,
    SingleRecordImportResponseModel,
)

BASE_URL = "https://dev.pvt.whitson.com/external/v2"
SESSION = {
    "id": 7,
    "source_format": "osdu",
    "status": "ready_for_review",
    "options": {"source_format": "osdu"},
    "summary": {"total_records": 1},
    "origin": "external",
    "managed_by": "external",
}
RECORD = {
    "id": 8,
    "import_session_id": 7,
    "entity_type": "sample",
    "action": "create",
    "status": "pending_review",
    "proposed_payload": {"entity_type": "sample", "name": "Sample 1"},
    "source_record": {"source_format": "osdu", "kind": "sample", "payload": {}},
}


@pytest.mark.parametrize("with_options", [False, True])
def test_create_import_session_uploads_archive_and_metadata(transport, httpx_mock, with_options):
    httpx_mock.add_response(method="POST", url=f"{BASE_URL}/import-sessions", json=SESSION)
    options = (
        ImportSessionCreateOptionsModel(region_id=42, allow_rafs=False) if with_options else None
    )
    result = WhitsonPVTClientV2(transport).import_sessions.create(b"archive-data", options)
    assert isinstance(result, ImportSessionModel)
    assert result.id == 7
    request = httpx_mock.get_requests()[-1]
    assert request.headers["content-type"].startswith("multipart/form-data;")
    assert b'filename="archive.zip"' in request.content
    assert b"archive-data" in request.content
    if with_options:
        assert b'"region_id":42' in request.content
        assert b'"allow_rafs":false' in request.content
    else:
        assert b"meta_data" not in request.content


def test_import_session_review_commit_and_delete(transport, httpx_mock):
    client = WhitsonPVTClientV2(transport)
    httpx_mock.add_response(method="GET", url=f"{BASE_URL}/import-sessions/7", json=SESSION)
    httpx_mock.add_response(
        method="GET", url=f"{BASE_URL}/import-sessions/7/records", json={"records": [RECORD]}
    )
    httpx_mock.add_response(
        method="PATCH",
        url=f"{BASE_URL}/import-sessions/7/records/8/resolution",
        json={**RECORD, "status": "accepted"},
    )
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/import-sessions/7/commit",
        json={"import_session_id": 7, "status": "committed", "records": []},
    )
    httpx_mock.add_response(method="DELETE", url=f"{BASE_URL}/import-sessions/7", status_code=204)

    assert client.import_sessions.get(7).id == 7
    records = client.import_sessions.list_records(7).records
    assert records and records[0].id == 8
    resolution = ImportRecordResolutionModel(action="create", status="accepted")
    assert client.import_sessions.update_resolution(7, 8, resolution).status == "accepted"
    assert json.loads(httpx_mock.get_requests()[-1].content) == {
        "action": "create",
        "status": "accepted",
    }
    result = client.import_sessions.commit(7, ImportCommitRequestModel(selected_record_ids=[8]))
    assert isinstance(result, ImportCommitResultModel)
    assert json.loads(httpx_mock.get_requests()[-1].content) == {"selected_record_ids": [8]}
    assert client.import_sessions.delete(7) is None


@pytest.mark.parametrize("selected_record_ids", [None, []])
def test_commit_preserves_selection_semantics(transport, httpx_mock, selected_record_ids):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/import-sessions/7/commit",
        json={"import_session_id": 7, "status": "ready_for_review", "records": []},
    )
    data = (
        ImportCommitRequestModel()
        if selected_record_ids is None
        else ImportCommitRequestModel(selected_record_ids=selected_record_ids)
    )
    WhitsonPVTClientV2(transport).import_sessions.commit(7, data)
    assert json.loads(httpx_mock.get_requests()[-1].content) == (
        {} if selected_record_ids is None else {"selected_record_ids": []}
    )


@pytest.mark.parametrize(
    "method,path",
    [
        ("import_osdu_sample", "samples"),
        ("import_osdu_sample_analysis", "sample-analyses"),
        ("import_osdu_report", "reports"),
        ("import_osdu_file", "files"),
    ],
)
def test_single_record_imports_are_wired_and_preserve_source_payload(
    transport, httpx_mock, method, path
):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/import-records/{path}",
        status_code=201,
        json={"import_session": SESSION, "record": RECORD},
    )
    payload = SingleRecordImportRequestModel(
        source_format="osdu",
        import_session_id=7,
        auto_commit=False,
        source_record=OSDURecordEnvelopeModel(
            id="namespace:record:123",
            kind="osdu:wks:sample:1.0.0",
            data={"ExtensionProperties": {"custom": "preserved"}},
        ),
    )
    method_fn = getattr(WhitsonPVTClientV2(transport).import_records, method)
    result = method_fn(payload)
    assert isinstance(result, SingleRecordImportResponseModel)
    assert result.import_session.id == 7
    assert json.loads(httpx_mock.get_requests()[-1].content) == payload.model_dump(
        exclude_unset=True
    )


def test_duplicate_archive_conflict_preserves_session_id(transport, httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/import-sessions",
        status_code=409,
        json={"message": "Duplicate archive", "import_session_id": 7},
    )
    with pytest.raises(APIError) as exc:
        WhitsonPVTClientV2(transport).import_sessions.create(b"archive-data")
    assert exc.value.status_code == 409
    assert exc.value.response_body == {"message": "Duplicate archive", "import_session_id": 7}

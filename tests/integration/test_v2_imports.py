from collections.abc import Callable

from whitson_pvt_sdk.v2 import WhitsonPVTClientV2
from whitson_pvt_sdk.v2.models import (
    ImportCommitRequestModel,
    ImportRecordResolutionModel,
    ImportSessionCreateOptionsModel,
)


def test_staged_archive_review_commit_and_cleanup(
    client_v2: WhitsonPVTClientV2, require_id: Callable[[str], int], created_region
):
    """Exercise the full workflow, committing only a skip (no native entity writes)."""
    archive, _ = client_v2.reports.export(require_id("REPORT_ID"), format="osdu")
    session = client_v2.import_sessions.create(
        archive, ImportSessionCreateOptionsModel(region_id=created_region.id)
    )
    try:
        assert client_v2.import_sessions.get(session.id).origin == "external"
        records = client_v2.import_sessions.list_records(session.id).records
        assert records
        record_id = records[0].id
        assert record_id is not None
        updated = client_v2.import_sessions.update_resolution(
            session.id, record_id, ImportRecordResolutionModel(action="skip", status="accepted")
        )
        assert updated.status == "accepted"
        empty = client_v2.import_sessions.commit(
            session.id, ImportCommitRequestModel(selected_record_ids=[])
        )
        assert empty.records == []
        result = client_v2.import_sessions.commit(
            session.id, ImportCommitRequestModel(selected_record_ids=[record_id])
        )
        assert result.records
        assert [record.import_record_id for record in result.records] == [record_id]
        assert result.records[0].action == "skip"
        assert result.records[0].status == "committed"
    finally:
        client_v2.import_sessions.delete(session.id)


def test_region_name_filter(client_v2: WhitsonPVTClientV2, created_region, run_name):
    regions = client_v2.regions.list_all(name=created_region.name, limit=1)
    assert any(region.id == created_region.id for region in regions)
    assert client_v2.regions.list_all(name=f"{run_name}-does-not-exist") == []

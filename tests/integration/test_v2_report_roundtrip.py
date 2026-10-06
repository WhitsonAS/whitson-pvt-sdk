"""Real SDK round trip. Requires a report with a PDF, wells, samples and experiments.

Only the staging session is deleted: the external API has no native-entity delete
endpoints. The uniquely named test region and imported entities remain for inspection.
"""

import hashlib
import json
from collections.abc import Callable
from io import BytesIO
from typing import Any, Literal
from zipfile import ZipFile

import pytest

from whitson_pvt_sdk.errors import NotFoundError
from whitson_pvt_sdk.v2 import WhitsonPVTClientV2
from whitson_pvt_sdk.v2.models import (
    CreateRegionModel,
    ImportCommitRequestModel,
    ImportRecordResolutionModel,
    ImportSessionCreateOptionsModel,
)


def _native_archive_content(data: bytes) -> dict[str, Any]:
    """Compare native data and file hashes, not ZIP metadata or export timestamps.

    Native payloads already use names rather than generated database IDs. Only
    top-level entity ordering is ignored; experiment stages/components stay ordered.
    """
    with ZipFile(BytesIO(data)) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("manifest.json"))
        files = manifest["files"]
        content = {
            section: json.loads(archive.read(files[section]))
            for section in ("report", "wells", "samples", "experiments")
        }
        for section in ("wells", "samples", "experiments"):
            content[section].sort(key=lambda item: json.dumps(item, sort_keys=True))
        content["counts"] = manifest["counts"]
        report_file = files["report_file"]
        content["report_file"] = (
            (report_file, hashlib.sha256(archive.read(report_file)).hexdigest())
            if report_file is not None
            else None
        )
        content["additional_files"] = sorted(
            (
                item["original_filename"],
                hashlib.sha256(archive.read(item["archive_path"])).hexdigest(),
            )
            for item in manifest["additional_files"]
        )
        return content


@pytest.mark.parametrize("archive_format", ["whitson_pvt", "osdu"])
def test_report_roundtrip(
    client_v2: WhitsonPVTClientV2,
    require_id: Callable[[str], int],
    run_name: str,
    archive_format: Literal["whitson_pvt", "osdu"],
):
    source_report_id = require_id("REPORT_ID")
    archive, filename = client_v2.reports.export(source_report_id, format="whitson_pvt")
    assert filename.endswith(".zip")
    expected = _native_archive_content(archive)
    assert expected["report_file"], "Choose a source report with an available PDF"
    for section in ("wells", "samples", "experiments"):
        assert expected[section], f"Choose a source report with {section}"

    if archive_format == "osdu":
        archive, _ = client_v2.reports.export(
            source_report_id,
            format="osdu",
            include_whitson_native_payload=True,
            include_structured_experiments=True,
        )

    # Export/validate first: a bad source must not create an unused test region.
    region = client_v2.regions.create(
        CreateRegionModel(
            name=f"{run_name}-{archive_format}-roundtrip",
            region_type="single_field",
            reservoir_type="Conventional",
            note=f"SDK round-trip copy of report {source_report_id}; retained for inspection.",
            public=False,
        )
    )
    print(f"Round-trip region: id={region.id}, name={region.name}", flush=True)
    assert client_v2.regions.get(region.id).name == region.name
    assert client_v2.wells.list_all(region.id) == []
    session = client_v2.import_sessions.create(
        archive,
        ImportSessionCreateOptionsModel(
            region_id=region.id,
            requested_source_format=archive_format,
            import_mode="whitson_high_fidelity" if archive_format == "osdu" else "auto",
        ),
    )
    print(f"Round-trip import session: id={session.id}", flush=True)
    try:
        fetched = client_v2.import_sessions.get(session.id)
        assert fetched.origin == "external"
        assert fetched.region_id == region.id
        assert fetched.source_format == archive_format
        assert fetched.status == "ready_for_review", fetched.model_dump()
        records = client_v2.import_sessions.list_records(session.id).records
        assert records
        assert {record.entity_type for record in records} >= {
            "report",
            "well",
            "sample",
            "experiment",
            "file",
        }
        record_ids = []
        for record in records:
            assert record.id is not None
            assert record.action == "create", record.model_dump()
            assert record.target_entity_id is None, record.model_dump()
            assert not record.errors, record.model_dump()
            assert record.status in {"pending_review", "accepted"}, record.model_dump()
            updated = client_v2.import_sessions.update_resolution(
                session.id,
                record.id,
                ImportRecordResolutionModel(action="create", status="accepted"),
            )
            assert updated.status == "accepted"
            assert updated.action == "create"
            record_ids.append(record.id)

        # An explicit empty selection must not import any records.
        empty = client_v2.import_sessions.commit(
            session.id, ImportCommitRequestModel(selected_record_ids=[])
        )
        assert empty.records == []
        assert client_v2.wells.list_all(region.id) == []
        uncommitted = client_v2.import_sessions.list_records(session.id).records
        assert uncommitted
        assert all(record.committed_entity_id is None for record in uncommitted)

        result = client_v2.import_sessions.commit(
            session.id, ImportCommitRequestModel(selected_record_ids=record_ids)
        )
        print(f"Round-trip commit: {result.model_dump_json()}", flush=True)
        assert result.import_session_id == session.id
        assert result.status == "committed", result.model_dump()
        assert result.records and len(result.records) == len(record_ids)
        assert {record.import_record_id for record in result.records} == set(record_ids)
        assert all(
            record.status == "committed"
            and record.action == "create"
            and record.committed_entity_id is not None
            and not record.errors
            for record in result.records
        ), result.model_dump()
        assert client_v2.import_sessions.get(session.id).status == "committed"
        committed = client_v2.import_sessions.list_records(session.id).records
        assert committed
        assert {(record.id, record.status, record.committed_entity_id) for record in committed} == {
            (record.import_record_id, record.status, record.committed_entity_id)
            for record in result.records
        }

        report_ids = [
            record.committed_entity_id for record in committed if record.entity_type == "report"
        ]
        assert len(report_ids) == 1
        imported_report_id = report_ids[0]
        assert imported_report_id is not None and imported_report_id != source_report_id

        wells = {
            well.id: client_v2.wells.get(well.id)
            for well in client_v2.wells.list_all(region.id, limit=1)
        }
        assert set(wells) == {
            record.committed_entity_id for record in committed if record.entity_type == "well"
        }
        assert all(well.region_id == region.id for well in wells.values())
        assert sorted(well.name for well in wells.values()) == sorted(
            well["name"] for well in expected["wells"]
        )
        sample_ids = {
            record.committed_entity_id for record in committed if record.entity_type == "sample"
        }
        assert {sample.id for well in wells.values() for sample in well.samples} == sample_ids
        actual_sample_keys = []
        for sample_id in sample_ids:
            assert sample_id is not None
            sample = client_v2.samples.get(sample_id)
            assert sample.well_id in wells
            actual_sample_keys.append((wells[sample.well_id].name, sample.name))
        assert sorted(actual_sample_keys) == sorted(
            (sample["well_name"], sample["name"]) for sample in expected["samples"]
        )
    finally:
        client_v2.import_sessions.delete(session.id)

    with pytest.raises(NotFoundError):
        client_v2.import_sessions.get(session.id)
    # Committed entities/files must survive deletion of their staging session.
    copied_archive, _ = client_v2.reports.export(imported_report_id, format="whitson_pvt")
    assert _native_archive_content(copied_archive) == expected
    # The source report must remain unchanged as well.
    source_after, _ = client_v2.reports.export(source_report_id, format="whitson_pvt")
    assert _native_archive_content(source_after) == expected

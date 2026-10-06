"""Exercise every single-record endpoint with records from a real SDK export."""

import json
from collections.abc import Callable
from io import BytesIO
from zipfile import ZipFile

from pydantic import TypeAdapter

from whitson_pvt_sdk.v2 import WhitsonPVTClientV2
from whitson_pvt_sdk.v2.models import (
    CreateRegionModel,
    CreateWellModel,
    ExperimentImportPayloadModel,
    Experiments,
    ImportCommitRequestModel,
    ImportRecordResolutionModel,
    OSDURecordEnvelopeModel,
    SingleRecordImportRequestModel,
    SingleRecordImportSuppliedContextModel,
)


def test_osdu_single_records_commit_replay_and_file_limit(
    client_v2: WhitsonPVTClientV2, require_id: Callable[[str], int], run_name: str
):
    report_id = require_id("REPORT_ID")
    archive, _ = client_v2.reports.export(report_id, format="osdu")
    native, _ = client_v2.reports.export(report_id)
    with ZipFile(BytesIO(native)) as source:
        experiments = json.loads(source.read("experiments.json"))
    with ZipFile(BytesIO(archive)) as source:
        manifest = json.loads(source.read("manifest.json"))
        records = [
            OSDURecordEnvelopeModel.model_validate_json(source.read(entry["path"]))
            for entry in manifest["records"]
        ]
    report_record = next(r for r in records if ":work-product--SamplesAnalysesReport:" in r.kind)
    analysis_record = next(
        r for r in records if ":work-product-component--SamplesAnalysis:" in r.kind
    )
    sample_record = next(
        r for r in records if r.id == analysis_record.data["SampleIDs"][0].rstrip(":")
    )
    file_record = next(r for r in records if ":dataset--File.Generic:" in r.kind)
    hints = sample_record.data["ExtensionProperties"]["whitson"]
    experiment = next(
        item
        for item in experiments
        if item["sample_name"] == sample_record.data["SampleName"]
        and item["well_name"] == hints["well_name"]
        and item["experiment"]["type"]
        == analysis_record.data["ExtensionProperties"]["whitson"]["native_experiment_type"]
    )

    region = client_v2.regions.create(
        CreateRegionModel(name=f"{run_name}-osdu-records", public=False)
    )
    well = client_v2.wells.create(CreateWellModel(name=hints["well_name"], region_id=region.id))
    print(f"OSDU record test region: id={region.id}, well={well.id}", flush=True)
    session_ids = set()
    try:
        report_request = SingleRecordImportRequestModel(
            source_format="osdu", region_id=region.id, source_record=report_record, auto_commit=True
        )
        report = client_v2.import_records.import_osdu_report(report_request)
        session_ids.add(report.import_session.id)
        assert report.created and report.committed, report.model_dump()
        assert report.record.committed_entity_id is not None
        assert report.commit_result and report.commit_result.status == "committed"
        imported_report_id = report.record.committed_entity_id
        assert imported_report_id != report_id
        print(f"OSDU single-record report: id={imported_report_id}", flush=True)

        replay = client_v2.import_records.import_osdu_report(
            report_request.model_copy(update={"import_session_id": report.import_session.id})
        )
        assert not replay.created and replay.committed
        assert replay.record.id == report.record.id
        assert replay.record.committed_entity_id == imported_report_id

        sample = client_v2.import_records.import_osdu_sample(
            SingleRecordImportRequestModel(
                source_format="osdu",
                region_id=region.id,
                source_record=sample_record,
                context=SingleRecordImportSuppliedContextModel(
                    well_id=well.id, report_id=imported_report_id
                ),
                auto_commit=True,
            )
        )
        session_ids.add(sample.import_session.id)
        assert sample.committed, sample.model_dump()
        sample_id = sample.record.committed_entity_id
        assert sample_id is not None
        fetched_sample = client_v2.samples.get(sample_id)
        assert fetched_sample.well_id == well.id
        assert fetched_sample.name == sample_record.data["SampleName"]

        analysis = client_v2.import_records.import_osdu_sample_analysis(
            SingleRecordImportRequestModel(
                source_format="osdu",
                region_id=region.id,
                source_record=analysis_record,
                context=SingleRecordImportSuppliedContextModel(
                    sample_id=sample_id, report_id=imported_report_id
                ),
            )
        )
        session_ids.add(analysis.import_session.id)
        assert analysis.created and not analysis.committed
        assert analysis.record.id is not None
        assert analysis.record.source_record.payload == analysis_record.model_dump(mode="json")
        # WKS metadata alone has no experiment stages; review with the actual native data.
        client_v2.import_sessions.update_resolution(
            analysis.import_session.id,
            analysis.record.id,
            ImportRecordResolutionModel(
                action="create",
                status="accepted",
                resolved_payload=ExperimentImportPayloadModel.model_validate(experiment),
            ),
        )
        committed = client_v2.import_sessions.commit(
            analysis.import_session.id,
            ImportCommitRequestModel(selected_record_ids=[analysis.record.id]),
        )
        assert committed.status == "committed", committed.model_dump()
        assert committed.records and committed.records[0].committed_entity_id is not None
        fetched_sample = client_v2.samples.get(sample_id)
        expected_experiment = TypeAdapter(Experiments).validate_python(experiment["experiment"])
        assert fetched_sample.experiments == [expected_experiment]

        file = client_v2.import_records.import_osdu_file(
            SingleRecordImportRequestModel(
                source_format="osdu",
                region_id=region.id,
                source_record=file_record,
                context=SingleRecordImportSuppliedContextModel(report_id=imported_report_id),
                auto_commit=True,
            )
        )
        session_ids.add(file.import_session.id)
        assert file.created and not file.committed
        assert file.record.status == "unsupported"
        assert file.record.committed_entity_id is None
        assert file.record.errors and any("file bytes" in error for error in file.record.errors)
        # JSON-only file import must not falsely claim to have transferred the PDF.
        assert file.commit_result is None
        copied, _ = client_v2.reports.export(imported_report_id)
        with ZipFile(BytesIO(copied)) as copy:
            assert json.loads(copy.read("manifest.json"))["files"]["report_file"] is None
            assert len(json.loads(copy.read("samples.json"))) == 1
    finally:
        for session_id in session_ids:
            client_v2.import_sessions.delete(session_id)

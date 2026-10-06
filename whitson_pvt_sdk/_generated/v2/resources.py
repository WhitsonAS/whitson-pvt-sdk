from __future__ import annotations

from collections.abc import Iterator
from io import BytesIO
from typing import TYPE_CHECKING

from whitson_pvt_sdk.shared.models import PaginationParams

if TYPE_CHECKING:
    from whitson_pvt_sdk.http import HTTPTransport

from pydantic import BaseModel

from whitson_pvt_sdk.shared.models import ImportArchiveOptions
from whitson_pvt_sdk.shared.pagination import Paginator
from whitson_pvt_sdk.v2.models import (
    CreateRegionModel,
    CreateSampleListModel,
    CreateSampleModel,
    CreateWellModel,
    FlashCalculationRequestModel,
    FlashCalculationResponseModel,
    GetBlackOilTableModel,
    GetFluidModelModel,
    GetProjectModel,
    GetProjectWithFluidModelsModel,
    GetRegionModel,
    GetSampleListModel,
    GetSampleModel,
    GetSimpleBlackOilTableModel,
    GetSimpleFluidModelModel,
    GetWellModel,
    GetWellSimpleModel,
    GorRecombinationCalculationRequestModel,
    GorRecombinationCalculationResponseModel,
    ImportCommitRequestModel,
    ImportCommitResultModel,
    ImportPreflightResultModel,
    ImportRecordListModel,
    ImportRecordModel,
    ImportRecordResolutionModel,
    ImportSessionCreateOptionsModel,
    ImportSessionModel,
    PaginatedBlackOilTablesModel,
    PaginatedFluidModelsModel,
    PaginatedProjectsModel,
    PaginatedRegionsModel,
    PaginatedWellsModel,
    PhaseEnvelopeCalculationRequestModel,
    PhaseEnvelopeCalculationResponseModel,
    ReportArchiveCommitResultModel,
    SampleToEosSlateConversionCalculationRequestModel,
    SampleToEosSlateConversionCalculationResponseModel,
    SaturationPressureCalculationRequestModel,
    SaturationPressureCalculationResponseModel,
    SeparatorProcessCalculationRequestModel,
    SeparatorProcessCalculationResponseModel,
    SingleRecordImportRequestModel,
    SingleRecordImportResponseModel,
    UpdateRegionModel,
    UpdateSampleListModel,
    UpdateSampleModel,
    UpdateWellModel,
    UpdateWellsListModel,
    VolumetricToCompositionConversionCalculationRequestModel,
    VolumetricToCompositionConversionCalculationResponseModel,
    WellsListModel,
)

ListType = list


class Regions:
    _transport: HTTPTransport

    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def list(
        self, cursor: str | None = None, limit: int | None = None, name: str | None = None
    ) -> PaginatedRegionsModel:
        body = self._transport.get(
            "/regions",
            params={
                **PaginationParams(cursor=cursor, limit=limit).model_dump(exclude_none=True),
                **{key: value for key, value in {"name": name}.items() if value is not None},
            },
        )
        return PaginatedRegionsModel.model_validate(body)

    def iterate(
        self, cursor: str | None = None, limit: int | None = None, name: str | None = None
    ) -> Iterator[GetRegionModel]:
        return Paginator.iterate(self.list, "regions", cursor=cursor, limit=limit, name=name)

    def list_all(
        self, cursor: str | None = None, limit: int | None = None, name: str | None = None
    ) -> ListType[GetRegionModel]:
        return Paginator.list_all(self.list, "regions", cursor=cursor, limit=limit, name=name)

    def create(self, data: CreateRegionModel) -> GetRegionModel:
        body = self._transport.post("/regions", body=data.model_dump(exclude_unset=True))
        return GetRegionModel.model_validate(body)

    def get(self, region_id: int) -> GetRegionModel:
        body = self._transport.get(f"/regions/{region_id}")
        return GetRegionModel.model_validate(body)

    def update(self, region_id: int, data: UpdateRegionModel) -> GetRegionModel:
        body = self._transport.put(
            f"/regions/{region_id}", body=data.model_dump(exclude_unset=True)
        )
        return GetRegionModel.model_validate(body)


class Wells:
    _transport: HTTPTransport

    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def list(
        self,
        region_id: int,
        cursor: str | None = None,
        limit: int | None = None,
        name: str | None = None,
    ) -> PaginatedWellsModel:
        body = self._transport.get(
            f"/regions/{region_id}/wells",
            params={
                **PaginationParams(cursor=cursor, limit=limit).model_dump(exclude_none=True),
                **{key: value for key, value in {"name": name}.items() if value is not None},
            },
        )
        return PaginatedWellsModel.model_validate(body)

    def iterate(
        self,
        region_id: int,
        cursor: str | None = None,
        limit: int | None = None,
        name: str | None = None,
    ) -> Iterator[GetWellSimpleModel]:
        return Paginator.iterate(
            self.list, "wells", region_id=region_id, cursor=cursor, limit=limit, name=name
        )

    def list_all(
        self,
        region_id: int,
        cursor: str | None = None,
        limit: int | None = None,
        name: str | None = None,
    ) -> ListType[GetWellSimpleModel]:
        return Paginator.list_all(
            self.list, "wells", region_id=region_id, cursor=cursor, limit=limit, name=name
        )

    def create(self, data: CreateWellModel) -> GetWellModel:
        body = self._transport.post(
            "/wells", body=data.model_dump(exclude={"samples"}, exclude_unset=True)
        )
        return GetWellModel.model_validate(body)

    def update_bulk(self, data: UpdateWellsListModel) -> WellsListModel:
        body = self._transport.put(
            "/wells/bulk", body=[model.model_dump(exclude_unset=True) for model in data.root]
        )
        return WellsListModel.model_validate(body)

    def get(self, well_id: int) -> GetWellModel:
        body = self._transport.get(f"/wells/{well_id}")
        return GetWellModel.model_validate(body)

    def update(self, well_id: int, data: UpdateWellModel) -> GetWellModel:
        body = self._transport.put(f"/wells/{well_id}", body=data.model_dump(exclude_unset=True))
        return GetWellModel.model_validate(body)


class Samples:
    _transport: HTTPTransport

    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def create(self, data: CreateSampleModel) -> GetSampleModel:
        body = self._transport.post("/samples", body=data.model_dump(exclude_unset=True))
        return GetSampleModel.model_validate(body)

    def create_bulk(self, data: CreateSampleListModel) -> GetSampleListModel:
        body = self._transport.post(
            "/samples/bulk", body=[model.model_dump(exclude_unset=True) for model in data.root]
        )
        return GetSampleListModel.model_validate(body)

    def update_bulk(self, data: UpdateSampleListModel) -> GetSampleListModel:
        body = self._transport.put(
            "/samples/bulk", body=[model.model_dump(exclude_unset=True) for model in data.root]
        )
        return GetSampleListModel.model_validate(body)

    def get(self, sample_id: int) -> GetSampleModel:
        body = self._transport.get(f"/samples/{sample_id}")
        return GetSampleModel.model_validate(body)

    def update(self, sample_id: int, data: UpdateSampleModel) -> GetSampleModel:
        body = self._transport.put(
            f"/samples/{sample_id}", body=data.model_dump(exclude_unset=True)
        )
        return GetSampleModel.model_validate(body)


class Projects:
    _transport: HTTPTransport

    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def get(self, project_id: int) -> GetProjectWithFluidModelsModel:
        body = self._transport.get(f"/projects/{project_id}")
        return GetProjectWithFluidModelsModel.model_validate(body)

    def list(
        self,
        region_id: int,
        cursor: str | None = None,
        limit: int | None = None,
        name: str | None = None,
    ) -> PaginatedProjectsModel:
        body = self._transport.get(
            f"/regions/{region_id}/projects",
            params={
                **PaginationParams(cursor=cursor, limit=limit).model_dump(exclude_none=True),
                **{key: value for key, value in {"name": name}.items() if value is not None},
            },
        )
        return PaginatedProjectsModel.model_validate(body)

    def iterate(
        self,
        region_id: int,
        cursor: str | None = None,
        limit: int | None = None,
        name: str | None = None,
    ) -> Iterator[GetProjectModel]:
        return Paginator.iterate(
            self.list, "projects", region_id=region_id, cursor=cursor, limit=limit, name=name
        )

    def list_all(
        self,
        region_id: int,
        cursor: str | None = None,
        limit: int | None = None,
        name: str | None = None,
    ) -> ListType[GetProjectModel]:
        return Paginator.list_all(
            self.list, "projects", region_id=region_id, cursor=cursor, limit=limit, name=name
        )


class FluidModels:
    _transport: HTTPTransport

    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def get(self, fluid_model_id: int) -> GetFluidModelModel:
        body = self._transport.get(f"/fluid-models/{fluid_model_id}")
        return GetFluidModelModel.model_validate(body)

    def list(
        self,
        project_id: int,
        cursor: str | None = None,
        limit: int | None = None,
        name: str | None = None,
    ) -> PaginatedFluidModelsModel:
        body = self._transport.get(
            f"/projects/{project_id}/fluid-models",
            params={
                **PaginationParams(cursor=cursor, limit=limit).model_dump(exclude_none=True),
                **{key: value for key, value in {"name": name}.items() if value is not None},
            },
        )
        return PaginatedFluidModelsModel.model_validate(body)

    def iterate(
        self,
        project_id: int,
        cursor: str | None = None,
        limit: int | None = None,
        name: str | None = None,
    ) -> Iterator[GetSimpleFluidModelModel]:
        return Paginator.iterate(
            self.list, "fluid_models", project_id=project_id, cursor=cursor, limit=limit, name=name
        )

    def list_all(
        self,
        project_id: int,
        cursor: str | None = None,
        limit: int | None = None,
        name: str | None = None,
    ) -> ListType[GetSimpleFluidModelModel]:
        return Paginator.list_all(
            self.list, "fluid_models", project_id=project_id, cursor=cursor, limit=limit, name=name
        )


class BlackOilTables:
    _transport: HTTPTransport

    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def get(self, black_oil_table_id: int) -> GetBlackOilTableModel:
        body = self._transport.get(f"/black-oil-tables/{black_oil_table_id}")
        return GetBlackOilTableModel.model_validate(body)

    def list(
        self,
        fluid_model_id: int,
        cursor: str | None = None,
        limit: int | None = None,
        name: str | None = None,
    ) -> PaginatedBlackOilTablesModel:
        body = self._transport.get(
            f"/fluid-models/{fluid_model_id}/black-oil-tables",
            params={
                **PaginationParams(cursor=cursor, limit=limit).model_dump(exclude_none=True),
                **{key: value for key, value in {"name": name}.items() if value is not None},
            },
        )
        return PaginatedBlackOilTablesModel.model_validate(body)

    def iterate(
        self,
        fluid_model_id: int,
        cursor: str | None = None,
        limit: int | None = None,
        name: str | None = None,
    ) -> Iterator[GetSimpleBlackOilTableModel]:
        return Paginator.iterate(
            self.list,
            "black_oil_tables",
            fluid_model_id=fluid_model_id,
            cursor=cursor,
            limit=limit,
            name=name,
        )

    def list_all(
        self,
        fluid_model_id: int,
        cursor: str | None = None,
        limit: int | None = None,
        name: str | None = None,
    ) -> ListType[GetSimpleBlackOilTableModel]:
        return Paginator.list_all(
            self.list,
            "black_oil_tables",
            fluid_model_id=fluid_model_id,
            cursor=cursor,
            limit=limit,
            name=name,
        )


class Reports:
    _transport: HTTPTransport

    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def import_archive(
        self, archive_data: bytes, options: ImportArchiveOptions | None = None
    ) -> ReportArchiveCommitResultModel:
        if options is None:
            options = ImportArchiveOptions()

        body = self._transport.post_multipart(
            "/reports/import",
            files={"file": ("archive.zip", BytesIO(archive_data), "application/zip")},
            data=_meta_data(options),
        )
        return ReportArchiveCommitResultModel.model_validate(body)

    def preflight_import(
        self, archive_data: bytes, options: ImportArchiveOptions | None = None
    ) -> ImportPreflightResultModel:
        if options is None:
            options = ImportArchiveOptions()

        body = self._transport.post_multipart(
            "/reports/import/preflight",
            files={"file": ("archive.zip", BytesIO(archive_data), "application/zip")},
            data=_meta_data(options),
        )
        return ImportPreflightResultModel.model_validate(body)

    def export(
        self,
        report_id: int,
        format: str | None = None,
        include_whitson_native_payload: bool | None = None,
        include_structured_experiments: bool | None = None,
    ) -> tuple[bytes, str]:
        data = self._transport.get_bytes(
            f"/reports/{report_id}/export",
            params={
                key: value
                for key, value in {
                    "format": format,
                    "include_whitson_native_payload": include_whitson_native_payload,
                    "include_structured_experiments": include_structured_experiments,
                }.items()
                if value is not None
            },
        )
        filename = f"report_{report_id}_export.zip"
        return data, filename


class Calculations:
    _transport: HTTPTransport

    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def calculate_flash(self, data: FlashCalculationRequestModel) -> FlashCalculationResponseModel:
        body = self._transport.post("/calculations/flash", body=data.model_dump(exclude_unset=True))
        return FlashCalculationResponseModel.model_validate(body)

    def calculate_gor_recombination(
        self, data: GorRecombinationCalculationRequestModel
    ) -> GorRecombinationCalculationResponseModel:
        body = self._transport.post(
            "/calculations/gor-recombination", body=data.model_dump(exclude_unset=True)
        )
        return GorRecombinationCalculationResponseModel.model_validate(body)

    def calculate_phase_envelope(
        self, data: PhaseEnvelopeCalculationRequestModel
    ) -> PhaseEnvelopeCalculationResponseModel:
        body = self._transport.post(
            "/calculations/phase-envelope", body=data.model_dump(exclude_unset=True)
        )
        return PhaseEnvelopeCalculationResponseModel.model_validate(body)

    def calculate_sample_to_eos_slate_conversion(
        self, data: SampleToEosSlateConversionCalculationRequestModel
    ) -> SampleToEosSlateConversionCalculationResponseModel:
        body = self._transport.post(
            "/calculations/sample-to-eos-slate-conversion", body=data.model_dump(exclude_unset=True)
        )
        return SampleToEosSlateConversionCalculationResponseModel.model_validate(body)

    def calculate_saturation_pressure(
        self, data: SaturationPressureCalculationRequestModel
    ) -> SaturationPressureCalculationResponseModel:
        body = self._transport.post(
            "/calculations/saturation-pressure", body=data.model_dump(exclude_unset=True)
        )
        return SaturationPressureCalculationResponseModel.model_validate(body)

    def calculate_separator_process(
        self, data: SeparatorProcessCalculationRequestModel
    ) -> SeparatorProcessCalculationResponseModel:
        body = self._transport.post(
            "/calculations/separator-process", body=data.model_dump(exclude_unset=True)
        )
        return SeparatorProcessCalculationResponseModel.model_validate(body)

    def calculate_volumetric_to_composition_conversion(
        self, data: VolumetricToCompositionConversionCalculationRequestModel
    ) -> VolumetricToCompositionConversionCalculationResponseModel:
        body = self._transport.post(
            "/calculations/volumetric-to-composition-conversion",
            body=data.model_dump(exclude_unset=True),
        )
        return VolumetricToCompositionConversionCalculationResponseModel.model_validate(body)


class ImportRecords:
    _transport: HTTPTransport

    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def import_osdu_file(
        self, data: SingleRecordImportRequestModel
    ) -> SingleRecordImportResponseModel:
        body = self._transport.post(
            "/import-records/files", body=data.model_dump(exclude_unset=True)
        )
        return SingleRecordImportResponseModel.model_validate(body)

    def import_osdu_report(
        self, data: SingleRecordImportRequestModel
    ) -> SingleRecordImportResponseModel:
        body = self._transport.post(
            "/import-records/reports", body=data.model_dump(exclude_unset=True)
        )
        return SingleRecordImportResponseModel.model_validate(body)

    def import_osdu_sample_analysis(
        self, data: SingleRecordImportRequestModel
    ) -> SingleRecordImportResponseModel:
        body = self._transport.post(
            "/import-records/sample-analyses", body=data.model_dump(exclude_unset=True)
        )
        return SingleRecordImportResponseModel.model_validate(body)

    def import_osdu_sample(
        self, data: SingleRecordImportRequestModel
    ) -> SingleRecordImportResponseModel:
        body = self._transport.post(
            "/import-records/samples", body=data.model_dump(exclude_unset=True)
        )
        return SingleRecordImportResponseModel.model_validate(body)


class ImportSessions:
    _transport: HTTPTransport

    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def create(
        self, archive_data: bytes, options: ImportSessionCreateOptionsModel | None = None
    ) -> ImportSessionModel:
        if options is None:
            options = ImportSessionCreateOptionsModel()

        body = self._transport.post_multipart(
            "/import-sessions",
            files={"file": ("archive.zip", BytesIO(archive_data), "application/zip")},
            data=_meta_data(options),
        )
        return ImportSessionModel.model_validate(body)

    def delete(self, import_session_id: int) -> None:
        self._transport.delete(f"/import-sessions/{import_session_id}")

    def get(self, import_session_id: int) -> ImportSessionModel:
        body = self._transport.get(f"/import-sessions/{import_session_id}")
        return ImportSessionModel.model_validate(body)

    def commit(
        self, import_session_id: int, data: ImportCommitRequestModel
    ) -> ImportCommitResultModel:
        body = self._transport.post(
            f"/import-sessions/{import_session_id}/commit", body=data.model_dump(exclude_unset=True)
        )
        return ImportCommitResultModel.model_validate(body)

    def list_records(self, import_session_id: int) -> ImportRecordListModel:
        body = self._transport.get(f"/import-sessions/{import_session_id}/records")
        return ImportRecordListModel.model_validate(body)

    def update_resolution(
        self, import_session_id: int, import_record_id: int, data: ImportRecordResolutionModel
    ) -> ImportRecordModel:
        body = self._transport.patch(
            f"/import-sessions/{import_session_id}/records/{import_record_id}/resolution",
            body=data.model_dump(exclude_unset=True),
        )
        return ImportRecordModel.model_validate(body)


def _meta_data(options: BaseModel) -> dict | None:
    dumped = options.model_dump(exclude_unset=True, exclude_defaults=True)
    if not dumped:
        return None
    return {"meta_data": options.model_dump_json(exclude_unset=True, exclude_defaults=True)}

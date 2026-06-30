from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from whitson_pvt_sdk.http import HTTPTransport

from whitson_pvt_sdk.shared.models import ImportArchiveOptions
from whitson_pvt_sdk.v1.models import (
    BlackOilTablesListModel,
    CreateRegionModel,
    CreateSampleListModel,
    CreateSampleModel,
    CreateWellModel,
    FluidModelsListModel,
    GetBlackOilTableModel,
    GetFluidModelModel,
    GetProjectWithFluidModelsModel,
    GetRegionModel,
    GetSampleListModel,
    GetSampleModel,
    GetWellModel,
    ImportCommitResultModel,
    ImportPreflightResultModel,
    ProjectsListModel,
    RegionsListModel,
    UpdateRegionModel,
    UpdateSampleListModel,
    UpdateSampleModel,
    UpdateWellModel,
    UpdateWellsListModel,
    WellsListModel,
)


class Regions:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def list(self) -> RegionsListModel:
        body = self._transport.get("/regions")
        return RegionsListModel.model_validate(body)

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
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def list(self, region_id: int) -> WellsListModel:
        body = self._transport.get(f"/regions/{region_id}/wells")
        return WellsListModel.model_validate(body)

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

    def create_well_deprecated(self, data: CreateWellModel) -> GetWellModel:
        body = self._transport.post("/wells/create", body=data.model_dump(exclude_unset=True))
        return GetWellModel.model_validate(body)

    def get(self, well_id: int) -> GetWellModel:
        body = self._transport.get(f"/wells/{well_id}")
        return GetWellModel.model_validate(body)

    def update(self, well_id: int, data: UpdateWellModel) -> GetWellModel:
        body = self._transport.put(f"/wells/{well_id}", body=data.model_dump(exclude_unset=True))
        return GetWellModel.model_validate(body)


class Samples:
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

    def create_sample_deprecated(self, data: CreateSampleModel) -> GetSampleModel:
        body = self._transport.post("/samples/create", body=data.model_dump(exclude_unset=True))
        return GetSampleModel.model_validate(body)

    def create_samples_deprecated(self, data: CreateSampleListModel) -> GetSampleListModel:
        body = self._transport.post(
            "/samples/create-many",
            body=[model.model_dump(exclude_unset=True) for model in data.root],
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
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def get(self, project_id: int) -> GetProjectWithFluidModelsModel:
        body = self._transport.get(f"/projects/{project_id}")
        return GetProjectWithFluidModelsModel.model_validate(body)

    def list(self, region_id: int) -> ProjectsListModel:
        body = self._transport.get(f"/regions/{region_id}/projects")
        return ProjectsListModel.model_validate(body)


class FluidModels:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def get(self, fluid_model_id: int) -> GetFluidModelModel:
        body = self._transport.get(f"/fluid-models/{fluid_model_id}")
        return GetFluidModelModel.model_validate(body)

    def list(self, project_id: int) -> FluidModelsListModel:
        body = self._transport.get(f"/projects/{project_id}/fluid-models")
        return FluidModelsListModel.model_validate(body)


class BlackOilTables:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def get(self, black_oil_table_id: int) -> GetBlackOilTableModel:
        body = self._transport.get(f"/black-oil-tables/{black_oil_table_id}")
        return GetBlackOilTableModel.model_validate(body)

    def list(self, fluid_model_id: int) -> BlackOilTablesListModel:
        body = self._transport.get(f"/fluid-models/{fluid_model_id}/black-oil-tables")
        return BlackOilTablesListModel.model_validate(body)


class Reports:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def import_archive(
        self, archive_data: bytes, options: ImportArchiveOptions | None = None
    ) -> ImportCommitResultModel:
        if options is None:
            options = ImportArchiveOptions()

        body = self._transport.post_multipart(
            "/reports/import",
            files={"file": ("archive.zip", BytesIO(archive_data), "application/zip")},
            data=_meta_data(options),
        )
        return ImportCommitResultModel.model_validate(body)

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

    def export(self, report_id: int) -> tuple[bytes, str]:
        data = self._transport.get_bytes(f"/reports/{report_id}/export")
        filename = f"report_{report_id}_export.zip"
        return data, filename


def _meta_data(options: ImportArchiveOptions) -> dict | None:
    dumped = options.model_dump(exclude_unset=True, exclude_defaults=True)
    if not dumped:
        return None
    return {"meta_data": options.model_dump_json(exclude_unset=True, exclude_defaults=True)}

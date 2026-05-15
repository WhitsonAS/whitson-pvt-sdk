from __future__ import annotations

from typing import TYPE_CHECKING

from whitson_pvt_sdk.v2 import (
    black_oil_tables,
    fluid_models,
    projects,
    regions,
    reports,
    samples,
    wells,
)

if TYPE_CHECKING:
    from whitson_pvt_sdk.http import HTTPTransport
    from whitson_pvt_sdk.models.manual import (
        ExternalImportArchiveOptions,
    )
    from whitson_pvt_sdk.models.v2._generated import (
        CreateRegionModel,
        CreateSampleListModel,
        CreateSampleModel,
        CreateWellModel,
        GetBlackOilTableModel,
        GetFluidModelModel,
        GetProjectWithFluidModelsModel,
        GetRegionModel,
        GetSampleListModel,
        GetSampleModel,
        GetWellModel,
        ImportCommitResultModel,
        ImportPreflightResultModel,
        PaginatedBlackOilTablesModel,
        PaginatedFluidModelsModel,
        PaginatedProjectsModel,
        PaginatedRegionsModel,
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

    def list(self) -> PaginatedRegionsModel:
        return regions.list_regions(self._transport)

    def get(self, region_id: int) -> GetRegionModel:
        return regions.get_region(self._transport, region_id)

    def create(self, data: CreateRegionModel) -> GetRegionModel:
        return regions.create_region(self._transport, data)

    def update(self, region_id: int, data: UpdateRegionModel) -> GetRegionModel:
        return regions.update_region(self._transport, region_id, data)


class Wells:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def list(self, region_id: int) -> WellsListModel:
        return wells.list_wells(self._transport, region_id)

    def get(self, well_id: int) -> GetWellModel:
        return wells.get_well(self._transport, well_id)

    def create(self, data: CreateWellModel) -> GetWellModel:
        return wells.create_well(self._transport, data)

    def update(self, well_id: int, data: UpdateWellModel) -> GetWellModel:
        return wells.update_well(self._transport, well_id, data)

    def update_bulk(self, data: UpdateWellsListModel) -> WellsListModel:
        return wells.update_wells_bulk(self._transport, data)


class Samples:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def list(self, well_id: int) -> GetSampleListModel:
        return samples.list_samples(self._transport, well_id)

    def get(self, sample_id: int) -> GetSampleModel:
        return samples.get_sample(self._transport, sample_id)

    def create(self, data: CreateSampleModel) -> GetSampleModel:
        return samples.create_sample(self._transport, data)

    def create_bulk(self, data: CreateSampleListModel) -> GetSampleListModel:
        return samples.create_samples_bulk(self._transport, data)

    def update(self, sample_id: int, data: UpdateSampleModel) -> GetSampleModel:
        return samples.update_sample(self._transport, sample_id, data)

    def update_bulk(self, data: UpdateSampleListModel) -> GetSampleListModel:
        return samples.update_samples_bulk(self._transport, data)

    def experiment_types(self, sample_id: int) -> list[str]:  # ty: ignore[invalid-type-form]
        return samples.get_sample_experiment_types(self._transport, sample_id)


class Projects:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def list(self, region_id: int) -> PaginatedProjectsModel:
        return projects.list_projects(self._transport, region_id)

    def get(self, project_id: int) -> GetProjectWithFluidModelsModel:
        return projects.get_project(self._transport, project_id)


class FluidModels:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def list(self, project_id: int) -> PaginatedFluidModelsModel:
        return fluid_models.list_fluid_models(self._transport, project_id)

    def get(self, fluid_model_id: int) -> GetFluidModelModel:
        return fluid_models.get_fluid_model(self._transport, fluid_model_id)


class BlackOilTables:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def list(self, fluid_model_id: int) -> PaginatedBlackOilTablesModel:
        return black_oil_tables.list_black_oil_tables(self._transport, fluid_model_id)

    def get(self, black_oil_table_id: int) -> GetBlackOilTableModel:
        return black_oil_tables.get_black_oil_table(self._transport, black_oil_table_id)


class Reports:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def export(self, report_id: int) -> tuple[bytes, str]:
        return reports.export_report(self._transport, report_id)

    def preflight_import(
        self, archive_data: bytes, options: ExternalImportArchiveOptions | None = None
    ) -> ImportPreflightResultModel:
        return reports.preflight_import(self._transport, archive_data, options)

    def import_archive(
        self, archive_data: bytes, options: ExternalImportArchiveOptions | None = None
    ) -> ImportCommitResultModel:
        return reports.import_report(self._transport, archive_data, options)

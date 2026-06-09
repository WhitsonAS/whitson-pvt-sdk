from __future__ import annotations

from typing import TYPE_CHECKING

from whitson_pvt_sdk._generated.v1 import (
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
    from whitson_pvt_sdk.shared.models import (
        ImportArchiveOptions,
    )
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
        return regions.list_regions(self._transport)

    def create(self, data: CreateRegionModel) -> GetRegionModel:
        return regions.create_region(self._transport, data)

    def get(self, region_id: int) -> GetRegionModel:
        return regions.get_region(self._transport, region_id)

    def update(self, region_id: int, data: UpdateRegionModel) -> GetRegionModel:
        return regions.update_region(self._transport, region_id, data)


class Wells:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def list(self, region_id: int) -> WellsListModel:
        return wells.list_wells_info(self._transport, region_id)

    def create(self, data: CreateWellModel) -> GetWellModel:
        return wells.create_well(self._transport, data)

    def update_bulk(self, data: UpdateWellsListModel) -> WellsListModel:
        return wells.update_wells(self._transport, data)

    def create_well_deprecated(self, data: CreateWellModel) -> GetWellModel:
        return wells.create_well_deprecated(self._transport, data)

    def get(self, well_id: int) -> GetWellModel:
        return wells.get_well(self._transport, well_id)

    def update(self, well_id: int, data: UpdateWellModel) -> GetWellModel:
        return wells.update_well(self._transport, well_id, data)


class Samples:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def create(self, data: CreateSampleModel) -> GetSampleModel:
        return samples.create_sample(self._transport, data)

    def create_bulk(self, data: CreateSampleListModel) -> GetSampleListModel:
        return samples.create_samples(self._transport, data)

    def update_bulk(self, data: UpdateSampleListModel) -> GetSampleListModel:
        return samples.update_samples(self._transport, data)

    def create_sample_deprecated(self, data: CreateSampleModel) -> GetSampleModel:
        return samples.create_sample_deprecated(self._transport, data)

    def create_samples_deprecated(self, data: CreateSampleListModel) -> GetSampleListModel:
        return samples.create_samples_deprecated(self._transport, data)

    def get(self, sample_id: int) -> GetSampleModel:
        return samples.get_sample(self._transport, sample_id)

    def update(self, sample_id: int, data: UpdateSampleModel) -> GetSampleModel:
        return samples.update_sample(self._transport, sample_id, data)


class Projects:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def get(self, project_id: int) -> GetProjectWithFluidModelsModel:
        return projects.get_project(self._transport, project_id)

    def list(self, region_id: int) -> ProjectsListModel:
        return projects.list_projects(self._transport, region_id)


class FluidModels:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def get(self, fluid_model_id: int) -> GetFluidModelModel:
        return fluid_models.get_fluid_model(self._transport, fluid_model_id)

    def list(self, project_id: int) -> FluidModelsListModel:
        return fluid_models.list_fluid_models(self._transport, project_id)


class BlackOilTables:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def get(self, black_oil_table_id: int) -> GetBlackOilTableModel:
        return black_oil_tables.get_black_oil_table(self._transport, black_oil_table_id)

    def list(self, fluid_model_id: int) -> BlackOilTablesListModel:
        return black_oil_tables.list_black_oil_tables(self._transport, fluid_model_id)


class Reports:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def import_archive(
        self, archive_data: bytes, options: ImportArchiveOptions | None = None
    ) -> ImportCommitResultModel:
        return reports.import_report(self._transport, archive_data, options)

    def preflight_import(
        self, archive_data: bytes, options: ImportArchiveOptions | None = None
    ) -> ImportPreflightResultModel:
        return reports.preflight_import(self._transport, archive_data, options)

    def export(self, report_id: int) -> tuple[bytes, str]:
        return reports.export_report(self._transport, report_id)

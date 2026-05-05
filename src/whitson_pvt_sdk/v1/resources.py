from typing import TYPE_CHECKING

from whitson_pvt_sdk.v1 import (
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
    from whitson_pvt_sdk.models import (
        ExternalBlackOilTablesListModel,
        ExternalCreateRegionModel,
        ExternalCreateSampleListModel,
        ExternalCreateSampleModel,
        ExternalCreateWellModel,
        ExternalFluidModelsListModel,
        ExternalGetBlackOilTableModel,
        ExternalGetFluidModelModel,
        ExternalGetProjectWithFluidModelsModel,
        ExternalGetRegionModel,
        ExternalGetSampleModel,
        ExternalGetWellModel,
        ExternalImportArchiveOptions,
        ExternalImportCommitResultModel,
        ExternalImportPreflightResultModel,
        ExternalProjectsListModel,
        ExternalRegionsListModel,
        ExternalUpdateRegionModel,
        ExternalUpdateSampleListModel,
        ExternalUpdateSampleModel,
        ExternalUpdateWellModel,
        ExternalUpdateWellsListModel,
        ExternalWellsListModel,
    )


class Regions:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def list(self) -> ExternalRegionsListModel:
        return regions.list_regions(self._transport)

    def get(self, region_id: int) -> ExternalGetRegionModel:
        return regions.get_region(self._transport, region_id)

    def create(self, data: ExternalCreateRegionModel) -> ExternalGetRegionModel:
        return regions.create_region(self._transport, data)

    def update(self, region_id: int, data: ExternalUpdateRegionModel) -> ExternalGetRegionModel:
        return regions.update_region(self._transport, region_id, data)


class Wells:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def list(self, region_id: int) -> ExternalWellsListModel:
        return wells.list_wells(self._transport, region_id)

    def get(self, well_id: int) -> ExternalGetWellModel:
        return wells.get_well(self._transport, well_id)

    def create(self, data: ExternalCreateWellModel) -> ExternalGetWellModel:
        return wells.create_well(self._transport, data)

    def update(self, well_id: int, data: ExternalUpdateWellModel) -> ExternalGetWellModel:
        return wells.update_well(self._transport, well_id, data)

    def update_bulk(self, data: ExternalUpdateWellsListModel) -> ExternalWellsListModel:
        return wells.update_wells_bulk(self._transport, data)


class Samples:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def list(self, well_id: int) -> list[ExternalGetSampleModel]:
        return samples.list_samples(self._transport, well_id)

    def get(self, sample_id: int) -> ExternalGetSampleModel:
        return samples.get_sample(self._transport, sample_id)

    def create(self, data: ExternalCreateSampleModel) -> ExternalGetSampleModel:
        return samples.create_sample(self._transport, data)

    def create_bulk(self, data: ExternalCreateSampleListModel) -> list[ExternalGetSampleModel]:
        return samples.create_samples_bulk(self._transport, data)

    def update(self, sample_id: int, data: ExternalUpdateSampleModel) -> ExternalGetSampleModel:
        return samples.update_sample(self._transport, sample_id, data)

    def update_bulk(self, data: ExternalUpdateSampleListModel) -> list[ExternalGetSampleModel]:
        return samples.update_samples_bulk(self._transport, data)

    def experiment_types(self, sample_id: int) -> list[str]:
        return samples.get_sample_experiment_types(self._transport, sample_id)


class Projects:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def list(self, region_id: int) -> ExternalProjectsListModel:
        return projects.list_projects(self._transport, region_id)

    def get(self, project_id: int) -> ExternalGetProjectWithFluidModelsModel:
        return projects.get_project(self._transport, project_id)


class FluidModels:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def list(self, project_id: int) -> ExternalFluidModelsListModel:
        return fluid_models.list_fluid_models(self._transport, project_id)

    def get(self, fluid_model_id: int) -> ExternalGetFluidModelModel:
        return fluid_models.get_fluid_model(self._transport, fluid_model_id)


class BlackOilTables:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def list(self, fluid_model_id: int) -> ExternalBlackOilTablesListModel:
        return black_oil_tables.list_black_oil_tables(self._transport, fluid_model_id)

    def get(self, black_oil_table_id: int) -> ExternalGetBlackOilTableModel:
        return black_oil_tables.get_black_oil_table(self._transport, black_oil_table_id)


class Reports:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def export(self, report_id: int) -> tuple[bytes, str]:
        return reports.export_report(self._transport, report_id)

    def preflight_import(
        self, archive_data: bytes, options: ExternalImportArchiveOptions | None = None
    ) -> ExternalImportPreflightResultModel:
        return reports.preflight_import(self._transport, archive_data, options)

    def import_(
        self, archive_data: bytes, options: ExternalImportArchiveOptions | None = None
    ) -> ExternalImportCommitResultModel:
        return reports.import_report(self._transport, archive_data, options)

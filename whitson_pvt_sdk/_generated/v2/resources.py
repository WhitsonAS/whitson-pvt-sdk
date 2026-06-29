from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from whitson_pvt_sdk._generated.v2 import (
    black_oil_tables,
    calculations,
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
        ImportCommitResultModel,
        ImportPreflightResultModel,
        PaginatedBlackOilTablesModel,
        PaginatedFluidModelsModel,
        PaginatedProjectsModel,
        PaginatedRegionsModel,
        PaginatedWellsModel,
        PhaseEnvelopeCalculationRequestModel,
        PhaseEnvelopeCalculationResponseModel,
        SampleToEosSlateConversionCalculationRequestModel,
        SampleToEosSlateConversionCalculationResponseModel,
        SaturationPressureCalculationRequestModel,
        SaturationPressureCalculationResponseModel,
        SeparatorProcessCalculationRequestModel,
        SeparatorProcessCalculationResponseModel,
        UpdateRegionModel,
        UpdateSampleListModel,
        UpdateSampleModel,
        UpdateWellModel,
        UpdateWellsListModel,
        WellsListModel,
    )

ListType = list


class Regions:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def list(self, cursor: str | None = None, limit: int | None = None) -> PaginatedRegionsModel:
        return regions.list_regions(self._transport, cursor, limit)

    def iterate(
        self, cursor: str | None = None, limit: int | None = None
    ) -> Iterator[GetRegionModel]:
        while True:
            page = self.list(cursor=cursor, limit=limit)
            yield from page.regions
            cursor = page.pagination.next_cursor
            if cursor is None:
                return

    def list_all(
        self, cursor: str | None = None, limit: int | None = None
    ) -> ListType[GetRegionModel]:
        return list(self.iterate(cursor=cursor, limit=limit))

    def create(self, data: CreateRegionModel) -> GetRegionModel:
        return regions.create_region(self._transport, data)

    def get(self, region_id: int) -> GetRegionModel:
        return regions.get_region(self._transport, region_id)

    def update(self, region_id: int, data: UpdateRegionModel) -> GetRegionModel:
        return regions.update_region(self._transport, region_id, data)


class Wells:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def list(
        self, region_id: int, cursor: str | None = None, limit: int | None = None
    ) -> PaginatedWellsModel:
        return wells.list_wells_info(self._transport, region_id, cursor, limit)

    def iterate(
        self, region_id: int, cursor: str | None = None, limit: int | None = None
    ) -> Iterator[GetWellSimpleModel]:
        while True:
            page = self.list(region_id=region_id, cursor=cursor, limit=limit)
            yield from page.wells
            cursor = page.pagination.next_cursor
            if cursor is None:
                return

    def list_all(
        self, region_id: int, cursor: str | None = None, limit: int | None = None
    ) -> ListType[GetWellSimpleModel]:
        return list(self.iterate(region_id=region_id, cursor=cursor, limit=limit))

    def create(self, data: CreateWellModel) -> GetWellModel:
        return wells.create_well(self._transport, data)

    def update_bulk(self, data: UpdateWellsListModel) -> WellsListModel:
        return wells.update_wells(self._transport, data)

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

    def get(self, sample_id: int) -> GetSampleModel:
        return samples.get_sample(self._transport, sample_id)

    def update(self, sample_id: int, data: UpdateSampleModel) -> GetSampleModel:
        return samples.update_sample(self._transport, sample_id, data)


class Projects:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def get(self, project_id: int) -> GetProjectWithFluidModelsModel:
        return projects.get_project(self._transport, project_id)

    def list(
        self, region_id: int, cursor: str | None = None, limit: int | None = None
    ) -> PaginatedProjectsModel:
        return projects.list_projects(self._transport, region_id, cursor, limit)

    def iterate(
        self, region_id: int, cursor: str | None = None, limit: int | None = None
    ) -> Iterator[GetProjectModel]:
        while True:
            page = self.list(region_id=region_id, cursor=cursor, limit=limit)
            yield from page.projects
            cursor = page.pagination.next_cursor
            if cursor is None:
                return

    def list_all(
        self, region_id: int, cursor: str | None = None, limit: int | None = None
    ) -> ListType[GetProjectModel]:
        return list(self.iterate(region_id=region_id, cursor=cursor, limit=limit))


class FluidModels:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def get(self, fluid_model_id: int) -> GetFluidModelModel:
        return fluid_models.get_fluid_model(self._transport, fluid_model_id)

    def list(
        self, project_id: int, cursor: str | None = None, limit: int | None = None
    ) -> PaginatedFluidModelsModel:
        return fluid_models.list_fluid_models(self._transport, project_id, cursor, limit)

    def iterate(
        self, project_id: int, cursor: str | None = None, limit: int | None = None
    ) -> Iterator[GetSimpleFluidModelModel]:
        while True:
            page = self.list(project_id=project_id, cursor=cursor, limit=limit)
            yield from page.fluid_models
            cursor = page.pagination.next_cursor
            if cursor is None:
                return

    def list_all(
        self, project_id: int, cursor: str | None = None, limit: int | None = None
    ) -> ListType[GetSimpleFluidModelModel]:
        return list(self.iterate(project_id=project_id, cursor=cursor, limit=limit))


class BlackOilTables:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def get(self, black_oil_table_id: int) -> GetBlackOilTableModel:
        return black_oil_tables.get_black_oil_table(self._transport, black_oil_table_id)

    def list(
        self, fluid_model_id: int, cursor: str | None = None, limit: int | None = None
    ) -> PaginatedBlackOilTablesModel:
        return black_oil_tables.list_black_oil_tables(
            self._transport, fluid_model_id, cursor, limit
        )

    def iterate(
        self, fluid_model_id: int, cursor: str | None = None, limit: int | None = None
    ) -> Iterator[GetSimpleBlackOilTableModel]:
        while True:
            page = self.list(fluid_model_id=fluid_model_id, cursor=cursor, limit=limit)
            yield from page.black_oil_tables
            cursor = page.pagination.next_cursor
            if cursor is None:
                return

    def list_all(
        self, fluid_model_id: int, cursor: str | None = None, limit: int | None = None
    ) -> ListType[GetSimpleBlackOilTableModel]:
        return list(self.iterate(fluid_model_id=fluid_model_id, cursor=cursor, limit=limit))


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


class Calculations:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def calculate_flash(self, data: FlashCalculationRequestModel) -> FlashCalculationResponseModel:
        return calculations.calculate_flash(self._transport, data)

    def calculate_gor_recombination(
        self, data: GorRecombinationCalculationRequestModel
    ) -> GorRecombinationCalculationResponseModel:
        return calculations.calculate_gor_recombination(self._transport, data)

    def calculate_phase_envelope(
        self, data: PhaseEnvelopeCalculationRequestModel
    ) -> PhaseEnvelopeCalculationResponseModel:
        return calculations.calculate_phase_envelope(self._transport, data)

    def calculate_sample_to_eos_slate_conversion(
        self, data: SampleToEosSlateConversionCalculationRequestModel
    ) -> SampleToEosSlateConversionCalculationResponseModel:
        return calculations.calculate_sample_to_eos_slate_conversion(self._transport, data)

    def calculate_saturation_pressure(
        self, data: SaturationPressureCalculationRequestModel
    ) -> SaturationPressureCalculationResponseModel:
        return calculations.calculate_saturation_pressure(self._transport, data)

    def calculate_separator_process(
        self, data: SeparatorProcessCalculationRequestModel
    ) -> SeparatorProcessCalculationResponseModel:
        return calculations.calculate_separator_process(self._transport, data)

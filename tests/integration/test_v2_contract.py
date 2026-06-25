from collections.abc import Callable

from whitson_pvt_sdk.v2 import WhitsonPVTClientV2
from whitson_pvt_sdk.v2.models import (
    CreateSampleListModel,
    UpdateRegionModel,
    UpdateSampleItemModel,
    UpdateSampleListModel,
    UpdateSampleModel,
    UpdateWellItemModel,
    UpdateWellModel,
    UpdateWellsListModel,
)


def test_auth_token_exchange(client_v2: WhitsonPVTClientV2):
    assert client_v2.get_access_token()


def test_regions_list(client_v2: WhitsonPVTClientV2):
    result = client_v2.regions.list(limit=1)
    assert result.regions is not None


def test_region_get(client_v2: WhitsonPVTClientV2, created_region):
    result = client_v2.regions.get(created_region.id)
    assert result.id == created_region.id


def test_region_update(client_v2: WhitsonPVTClientV2, created_region):
    result = client_v2.regions.update(
        created_region.id, UpdateRegionModel(note="Updated by integration test.")
    )
    assert result.id == created_region.id
    assert result.note == "Updated by integration test."


def test_projects_list(client_v2: WhitsonPVTClientV2, created_region):
    result = client_v2.projects.list(created_region.id, limit=1)
    assert result.projects is not None


def test_project_get(client_v2: WhitsonPVTClientV2, require_id: Callable[[str], int]):
    result = client_v2.projects.get(require_id("PROJECT_ID"))
    assert result.id == require_id("PROJECT_ID")


def test_wells_list(client_v2: WhitsonPVTClientV2, created_region, created_well):
    result = client_v2.wells.list(created_region.id, limit=10)
    assert any(well.id == created_well.id for well in result.wells)


def test_well_create(created_well_result):
    if isinstance(created_well_result, Exception):
        raise created_well_result
    assert created_well_result.id


def test_well_get(client_v2: WhitsonPVTClientV2, created_well):
    result = client_v2.wells.get(created_well.id)
    assert result.id == created_well.id


def test_well_update(client_v2: WhitsonPVTClientV2, created_well):
    result = client_v2.wells.update(
        created_well.id, UpdateWellModel(name=f"{created_well.name}-updated")
    )
    assert result.id == created_well.id


def test_well_update_bulk(client_v2: WhitsonPVTClientV2, created_well):
    result = client_v2.wells.update_bulk(
        UpdateWellsListModel(root=[UpdateWellItemModel(id=created_well.id, uwi=created_well.uwi)])
    )
    assert any(well.id == created_well.id for well in result.wells)


def test_samples_list(client_v2: WhitsonPVTClientV2, created_well):
    result = client_v2.samples.list(created_well.id)
    assert result.samples is not None


def test_sample_create(created_sample_result):
    if isinstance(created_sample_result, Exception):
        raise created_sample_result
    assert created_sample_result.id


def test_sample_get(client_v2: WhitsonPVTClientV2, created_sample):
    result = client_v2.samples.get(created_sample.id)
    assert result.id == created_sample.id


def test_sample_update(client_v2: WhitsonPVTClientV2, created_sample):
    result = client_v2.samples.update(
        created_sample.id, UpdateSampleModel(note="Updated by integration test.")
    )
    assert result.id == created_sample.id


def test_sample_create_bulk(client_v2: WhitsonPVTClientV2, sample_factory):
    result = client_v2.samples.create_bulk(
        CreateSampleListModel(root=[sample_factory("bulk-sample")])
    )
    assert result.samples


def test_sample_update_bulk(client_v2: WhitsonPVTClientV2, created_sample):
    result = client_v2.samples.update_bulk(
        UpdateSampleListModel(
            root=[
                UpdateSampleItemModel(
                    id=created_sample.id, note="Bulk updated by integration test."
                )
            ]
        )
    )
    assert any(sample.id == created_sample.id for sample in result.samples)


def test_fluid_models_list(client_v2: WhitsonPVTClientV2, require_id: Callable[[str], int]):
    result = client_v2.fluid_models.list(require_id("PROJECT_ID"), limit=1)
    assert result.fluid_models is not None


def test_fluid_model_get(client_v2: WhitsonPVTClientV2, require_id: Callable[[str], int]):
    result = client_v2.fluid_models.get(require_id("FLUID_MODEL_ID"))
    assert result.id == require_id("FLUID_MODEL_ID")


def test_black_oil_tables_list(client_v2: WhitsonPVTClientV2, require_id: Callable[[str], int]):
    result = client_v2.black_oil_tables.list(require_id("FLUID_MODEL_ID"), limit=1)
    assert result.black_oil_tables is not None


def test_black_oil_table_get(client_v2: WhitsonPVTClientV2, require_id: Callable[[str], int]):
    result = client_v2.black_oil_tables.get(require_id("BLACK_OIL_TABLE_ID"))
    assert result.id == require_id("BLACK_OIL_TABLE_ID")


def test_report_export(client_v2: WhitsonPVTClientV2, require_id: Callable[[str], int]):
    archive, filename = client_v2.reports.export(require_id("REPORT_ID"))
    assert archive
    assert filename

from types import SimpleNamespace

from ..http import HTTPTransport


def regions(transport: HTTPTransport) -> SimpleNamespace:
    from .regions import create_region, get_region, list_regions, update_region

    return SimpleNamespace(
        list=lambda: list_regions(transport),
        get=lambda region_id: get_region(transport, region_id),
        create=lambda data: create_region(transport, data),
        update=lambda region_id, data: update_region(transport, region_id, data),
    )


def wells(transport: HTTPTransport) -> SimpleNamespace:
    from .wells import create_well, get_well, list_wells, update_well, update_wells_bulk

    return SimpleNamespace(
        list=lambda region_id: list_wells(transport, region_id),
        get=lambda well_id: get_well(transport, well_id),
        create=lambda data: create_well(transport, data),
        update=lambda well_id, data: update_well(transport, well_id, data),
        update_bulk=lambda data: update_wells_bulk(transport, data),
    )


def samples(transport: HTTPTransport) -> SimpleNamespace:
    from .samples import (
        create_sample,
        create_samples_bulk,
        get_sample,
        get_sample_experiment_types,
        list_samples,
        update_sample,
        update_samples_bulk,
    )

    return SimpleNamespace(
        list=lambda well_id: list_samples(transport, well_id),
        get=lambda sample_id: get_sample(transport, sample_id),
        create=lambda data: create_sample(transport, data),
        create_bulk=lambda data: create_samples_bulk(transport, data),
        update=lambda sample_id, data: update_sample(transport, sample_id, data),
        update_bulk=lambda data: update_samples_bulk(transport, data),
        experiment_types=lambda sample_id: get_sample_experiment_types(transport, sample_id),
    )


def projects(transport: HTTPTransport) -> SimpleNamespace:
    from .projects import get_project, list_projects

    return SimpleNamespace(
        list=lambda region_id: list_projects(transport, region_id),
        get=lambda project_id: get_project(transport, project_id),
    )


def fluid_models(transport: HTTPTransport) -> SimpleNamespace:
    from .fluid_models import get_fluid_model, list_fluid_models

    return SimpleNamespace(
        list=lambda project_id: list_fluid_models(transport, project_id),
        get=lambda fluid_model_id: get_fluid_model(transport, fluid_model_id),
    )


def black_oil_tables(transport: HTTPTransport) -> SimpleNamespace:
    from .black_oil_tables import get_black_oil_table, list_black_oil_tables

    return SimpleNamespace(
        list=lambda fluid_model_id: list_black_oil_tables(transport, fluid_model_id),
        get=lambda black_oil_table_id: get_black_oil_table(transport, black_oil_table_id),
    )


def reports(transport: HTTPTransport) -> SimpleNamespace:
    from .reports import export_report, import_report, preflight_import

    return SimpleNamespace(
        export=lambda report_id: export_report(transport, report_id),
        preflight_import=lambda archive_data, options=None: preflight_import(
            transport, archive_data, options
        ),
        import_=lambda archive_data, options=None: import_report(transport, archive_data, options),
    )

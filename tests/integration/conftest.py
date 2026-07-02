import os
import uuid
from collections.abc import Iterator

import pytest

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.shared.models import ClientCredentials
from whitson_pvt_sdk.v2 import WhitsonPVTClientV2
from whitson_pvt_sdk.v2.models import (
    CCEExperimentModel,
    CCEStageModel,
    CompositionComponentModel,
    CompositionModel,
    CreateRegionModel,
    CreateSampleModel,
    CreateWellModel,
    GetWellModel,
)


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return None
    return value


def _env_int(name: str) -> int | None:
    value = _env(name)
    if value is None:
        return None
    return int(value)


def _sample_model(name: str, well_id: int) -> CreateSampleModel:
    return CreateSampleModel(
        name=name,
        type="REC",
        fluid_type="Oil",
        well_id=well_id,
        recombined_fluid_composition=CompositionModel(
            components=[
                CompositionComponentModel(name="C1", input_name="C1", molar_amount=0.8),
                CompositionComponentModel(name="C2", input_name="C2", molar_amount=0.2),
            ]
        ),
        experiments=[
            CCEExperimentModel(
                name="Integration CCE",
                type="CCE",
                saturation_pressure_type="Bubblepoint",
                temperature=50.0,
                temperature_unit="C",
                stages=[CCEStageModel(is_saturation_pressure=True, pressure=100.0)],
            )
        ],
    )


def pytest_collection_modifyitems(items):
    for item in items:
        if "integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def integration_base_url() -> str:
    value = _env("WHITSON_INTEGRATION_BASE_URL")
    if value is None:
        pytest.skip("Set WHITSON_INTEGRATION_BASE_URL to run integration tests")
    return value


@pytest.fixture(scope="session")
def integration_credentials() -> ClientCredentials:
    client_id = _env("WHITSON_INTEGRATION_CLIENT_ID")
    client_secret = _env("WHITSON_INTEGRATION_CLIENT_SECRET")
    if client_id is None or client_secret is None:
        pytest.skip(
            "Set WHITSON_INTEGRATION_CLIENT_ID and "
            "WHITSON_INTEGRATION_CLIENT_SECRET to run integration tests"
        )
    return ClientCredentials(client_id=client_id, client_secret=client_secret)


@pytest.fixture(scope="session")
def client_v2(
    integration_base_url: str, integration_credentials: ClientCredentials
) -> Iterator[WhitsonPVTClientV2]:
    client = WhitsonPVTClient(
        credentials=integration_credentials,
        base_url=integration_base_url,
        version="v2",
    )
    try:
        yield client
    finally:
        client._transport.close()


@pytest.fixture(scope="session")
def ids() -> dict[str, int]:
    return {
        name: value
        for name in (
            "PROJECT_ID",
            "FLUID_MODEL_ID",
            "BLACK_OIL_TABLE_ID",
            "REPORT_ID",
        )
        if (value := _env_int(f"WHITSON_INTEGRATION_{name}")) is not None
    }


@pytest.fixture(scope="session")
def require_id(ids: dict[str, int]):
    def get(name: str) -> int:
        if name not in ids:
            pytest.skip(f"Set WHITSON_INTEGRATION_{name} to run this integration test")
        return ids[name]

    return get


@pytest.fixture(scope="session")
def run_name() -> str:
    return f"sdk-it-{uuid.uuid4().hex[:12]}"


@pytest.fixture(scope="session")
def created_region(client_v2: WhitsonPVTClientV2, run_name: str):
    return client_v2.regions.create(
        CreateRegionModel(
            name=f"{run_name}-region",
            region_type="single_field",
            reservoir_type="Conventional",
            note="Created by whitson-pvt-sdk integration tests.",
            public=False,
        )
    )


@pytest.fixture(scope="session")
def created_well_result(client_v2: WhitsonPVTClientV2, created_region, run_name: str):
    try:
        return client_v2.wells.create(
            CreateWellModel(
                name=f"{run_name}-well",
                region_id=created_region.id,
                uwi=f"{run_name}-uwi",
            )
        )
    except Exception as exc:
        return exc


@pytest.fixture(scope="session")
def created_well(client_v2: WhitsonPVTClientV2, created_well_result, created_region, run_name: str):
    if isinstance(created_well_result, Exception):
        body = {
            "name": f"{run_name}-well-setup",
            "region_id": created_region.id,
            "uwi": f"{run_name}-uwi-setup",
            "samples": [],
        }
        try:
            return GetWellModel.model_validate(client_v2._transport.post("/wells", body=body))
        except Exception as exc:
            pytest.skip(f"Creating integration well failed: {exc}")
    return created_well_result


@pytest.fixture(scope="session")
def created_sample_result(client_v2: WhitsonPVTClientV2, created_well, run_name: str):
    try:
        return client_v2.samples.create(_sample_model(f"{run_name}-sample", created_well.id))
    except Exception as exc:
        return exc


@pytest.fixture(scope="session")
def created_sample(created_sample_result):
    if isinstance(created_sample_result, Exception):
        pytest.skip(f"Creating integration sample failed: {created_sample_result}")
    return created_sample_result


@pytest.fixture(scope="session")
def sample_factory(created_well, run_name: str):
    def make(name: str) -> CreateSampleModel:
        return _sample_model(f"{run_name}-{name}", created_well.id)

    return make

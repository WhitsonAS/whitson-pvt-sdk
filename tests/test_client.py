import pytest

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.shared.models import RetryConfig
from whitson_pvt_sdk.v2 import WhitsonPVTClientV2
from whitson_pvt_sdk.v2.resources import (
    BlackOilTables as V2BlackOilTables,
)
from whitson_pvt_sdk.v2.resources import (
    FluidModels as V2FluidModels,
)
from whitson_pvt_sdk.v2.resources import (
    Projects as V2Projects,
)
from whitson_pvt_sdk.v2.resources import (
    Regions as V2Regions,
)
from whitson_pvt_sdk.v2.resources import (
    Reports as V2Reports,
)
from whitson_pvt_sdk.v2.resources import (
    Samples as V2Samples,
)
from whitson_pvt_sdk.v2.resources import (
    Wells as V2Wells,
)


def test_defaults_to_v2(credentials, base_url):
    client = WhitsonPVTClient(credentials=credentials, base_url=base_url)
    assert isinstance(client, WhitsonPVTClientV2)
    assert isinstance(client.regions, V2Regions)
    assert isinstance(client.wells, V2Wells)
    assert isinstance(client.samples, V2Samples)
    assert isinstance(client.projects, V2Projects)
    assert isinstance(client.fluid_models, V2FluidModels)
    assert isinstance(client.black_oil_tables, V2BlackOilTables)
    assert isinstance(client.reports, V2Reports)


@pytest.mark.parametrize(
    ("version", "message"),
    [
        ("v1", r"v1 was removed in whitson-pvt-sdk 1\.4\.0.*1\.3\.x still supports v1"),
        ("v3", "Unknown version"),
    ],
)
def test_unsupported_version_raises_value_error(credentials, base_url, version, message):
    with pytest.raises(ValueError, match=message):
        WhitsonPVTClient(credentials=credentials, base_url=base_url, version=version)


def test_passes_api_token_url_by_default(credentials, base_url):
    client = WhitsonPVTClient(credentials=credentials, base_url=base_url)
    transport = client._transport
    assert transport._token_url == "https://dev.pvt.whitson.com/external/v2/auth/token"
    assert transport._credentials == credentials
    assert transport._retry_config.max_attempts == RetryConfig().max_attempts


def test_client_exposes_access_token(credentials, base_url, httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=f"{base_url}/external/v2/auth/token",
        json={"access_token": "fake-token", "expires_in": 86400, "token_type": "Bearer"},
    )
    client = WhitsonPVTClient(credentials=credentials, base_url=base_url)
    assert client.get_access_token() == "fake-token"


def test_passes_retry_config(credentials, base_url):
    retry_config = RetryConfig(max_attempts=1)
    client = WhitsonPVTClient(credentials=credentials, base_url=base_url, retry_config=retry_config)
    assert client._transport._retry_config is retry_config


@pytest.mark.usefixtures("auth_mock")
def test_passes_timeout_config(credentials, base_url, httpx_mock):
    client = WhitsonPVTClient(
        credentials=credentials, base_url=base_url, timeout=12.5, file_timeout=19.5
    )
    regions_url = f"{base_url}/external/v2/regions"
    export_url = f"{base_url}/external/v2/reports/1/export"
    httpx_mock.add_response(
        url=regions_url,
        json={"regions": [], "pagination": {"next_cursor": None, "prev_cursor": None}},
    )
    httpx_mock.add_response(url=export_url, content=b"zip")
    client.regions.list()
    client.reports.export(report_id=1)
    assert [
        r.extensions["timeout"]["read"]
        for r in httpx_mock.get_requests()
        if str(r.url) in (regions_url, export_url)
    ] == [12.5, 19.5]

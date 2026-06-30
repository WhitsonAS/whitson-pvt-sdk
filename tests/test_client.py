import warnings

import pytest

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk._generated.v1.resources import (
    Samples as GeneratedV1Samples,
)
from whitson_pvt_sdk.shared.models import RetryConfig
from whitson_pvt_sdk.v1 import WhitsonPVTClientV1
from whitson_pvt_sdk.v1.resources import (
    BlackOilTables as V1BlackOilTables,
)
from whitson_pvt_sdk.v1.resources import (
    FluidModels as V1FluidModels,
)
from whitson_pvt_sdk.v1.resources import (
    Projects as V1Projects,
)
from whitson_pvt_sdk.v1.resources import (
    Regions as V1Regions,
)
from whitson_pvt_sdk.v1.resources import (
    Reports as V1Reports,
)
from whitson_pvt_sdk.v1.resources import (
    Samples as V1Samples,
)
from whitson_pvt_sdk.v1.resources import (
    Wells as V1Wells,
)
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


def test_v1_loads_v1_resources(credentials, base_url):
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        client = WhitsonPVTClient(credentials=credentials, base_url=base_url, version="v1")
    assert isinstance(client, WhitsonPVTClientV1)
    assert isinstance(client.regions, V1Regions)
    assert isinstance(client.wells, V1Wells)
    assert isinstance(client.samples, V1Samples)
    assert type(client.samples) is not GeneratedV1Samples
    assert isinstance(client.projects, V1Projects)
    assert isinstance(client.fluid_models, V1FluidModels)
    assert isinstance(client.black_oil_tables, V1BlackOilTables)
    assert isinstance(client.reports, V1Reports)


def test_v1_emits_deprecation_warning(credentials, base_url):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        WhitsonPVTClient(credentials=credentials, base_url=base_url, version="v1")
    deprecations = [x for x in w if issubclass(x.category, DeprecationWarning)]
    assert len(deprecations) == 1
    assert "deprecated" in str(deprecations[0].message)


def test_unknown_version_raises_value_error(credentials, base_url):
    with pytest.raises(ValueError, match="Unknown version"):
        WhitsonPVTClient(credentials=credentials, base_url=base_url, version="v3")


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


def test_passes_timeout_config(credentials, base_url):
    client = WhitsonPVTClient(
        credentials=credentials, base_url=base_url, timeout=12.5, file_timeout=19.5
    )
    assert client._transport._http.timeout.read == 12.5
    assert client._transport._file_timeout == 19.5

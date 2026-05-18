import warnings
from unittest.mock import patch

import pytest

from whitson_pvt_sdk import WhitsonPVTClient
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


def _create_client(credentials, base_url, **kwargs):
    with patch("whitson_pvt_sdk.http.TokenManager") as mock:
        mock.return_value.get_token.return_value = "fake-token"
        return WhitsonPVTClient(credentials=credentials, base_url=base_url, **kwargs)


def test_defaults_to_v2(credentials, base_url):
    client = _create_client(credentials, base_url)
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
        client = _create_client(credentials, base_url, version="v1")
    assert isinstance(client.regions, V1Regions)
    assert isinstance(client.wells, V1Wells)
    assert isinstance(client.samples, V1Samples)
    assert isinstance(client.projects, V1Projects)
    assert isinstance(client.fluid_models, V1FluidModels)
    assert isinstance(client.black_oil_tables, V1BlackOilTables)
    assert isinstance(client.reports, V1Reports)


def test_v1_emits_deprecation_warning(credentials, base_url):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        _create_client(credentials, base_url, version="v1")
    deprecations = [x for x in w if issubclass(x.category, DeprecationWarning)]
    assert len(deprecations) == 1
    assert "deprecated" in str(deprecations[0].message)


def test_unknown_version_raises_value_error(credentials, base_url):
    with patch("whitson_pvt_sdk.http.TokenManager"):
        with pytest.raises(ValueError, match="Unknown version"):
            WhitsonPVTClient(credentials=credentials, base_url=base_url, version="v3")


def test_passes_auth0_overrides(credentials, base_url):
    with patch("whitson_pvt_sdk.http.TokenManager") as mock:
        mock.return_value.get_token.return_value = "fake-token"
        WhitsonPVTClient(
            credentials=credentials,
            base_url=base_url,
            auth0_domain="custom.auth0.com",
            audience="https://custom.api",
        )
    mock.assert_called_once_with(
        credentials,
        auth0_domain="custom.auth0.com",
        audience="https://custom.api",
    )

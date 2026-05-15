import warnings

from .http import HTTPTransport

__version__ = "0.1.0"

_DEPRECATED: dict[str, str] = {}
"""Map of deprecated versions to their replacements.
Example: _DEPRECATED = {"v1": "v2"} — v1 still works but warns.
"""

_SUPPORTED = frozenset({"v1", "v2"})


class WhitsonPVTClient:
    """whitson PVT SDK — HTTP client for the whitson PVT external API.

    Usage::

        from whitson_pvt_sdk import WhitsonPVTClient
        from whitson_pvt_sdk.models.manual import ClientCredentials

        client = WhitsonPVTClient(
            credentials=ClientCredentials(client_id="...", client_secret="..."),
            base_url="https://internal.pvt.whitson.com",
            version="v1",
        )
        regions = client.regions.list()
        well = client.wells.get(well_id=123)
    """

    def __init__(
        self,
        *,
        credentials,
        base_url: str,
        version: str = "v1",
        auth0_domain: str | None = None,
        audience: str | None = None,
    ) -> None:
        transport = HTTPTransport(
            credentials,
            base_url,
            version=version,
            auth0_domain=auth0_domain,
            audience=audience,
        )

        if version in _DEPRECATED:
            warnings.warn(
                f"Version {version!r} is deprecated. Use {_DEPRECATED[version]!r} instead.",
                DeprecationWarning,
                stacklevel=2,
            )

        match version:
            case "v1":
                from .v1.resources import (
                    BlackOilTables,
                    FluidModels,
                    Projects,
                    Regions,
                    Reports,
                    Samples,
                    Wells,
                )
            case "v2":
                from .v2.resources import (
                    BlackOilTables,
                    FluidModels,
                    Projects,
                    Regions,
                    Reports,
                    Samples,
                    Wells,
                )
            case _:
                if version in _SUPPORTED:
                    raise RuntimeError(
                        f"Version {version} is supported but not yet wired. "
                        "This is a bug — please report it."
                    )
                raise ValueError(
                    f"Unknown version: {version!r}. Supported versions: {sorted(_SUPPORTED)}"
                )

        self.regions = Regions(transport)
        self.wells = Wells(transport)
        self.samples = Samples(transport)
        self.projects = Projects(transport)
        self.fluid_models = FluidModels(transport)
        self.black_oil_tables = BlackOilTables(transport)
        self.reports = Reports(transport)


__all__ = ["WhitsonPVTClient"]

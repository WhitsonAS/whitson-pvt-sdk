"""whitson PVT SDK — HTTP client for the whitson PVT external API."""

import warnings

from .http import HTTPTransport

__version__ = "0.1.0"

"""Map of deprecated versions to their replacements.
Example: _DEPRECATED = {"v1": "v2"} — v1 still works but warns.
"""
_DEPRECATED: dict[str, str] = {}

_SUPPORTED = frozenset({"v1", "v2"})


class WhitsonPVTClient:
    """whitson PVT SDK — HTTP client for the whitson PVT external API.

    Usage::

        from pvt_sdk import WhitsonPVTClient
        from pvt_sdk._models import ClientCredentials

        client = WhitsonPVTClient(
            credentials=ClientCredentials(client_id="...", client_secret="..."),
            base_url="https://api.whitson.com",
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
                from .v1.factory import (
                    black_oil_tables,
                    fluid_models,
                    projects,
                    regions,
                    reports,
                    samples,
                    wells,
                )
            case "v2":
                from .v2.factory import (
                    black_oil_tables,
                    fluid_models,
                    projects,
                    regions,
                    reports,
                    samples,
                    wells,
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

        self.regions = regions(transport)
        self.wells = wells(transport)
        self.samples = samples(transport)
        self.projects = projects(transport)
        self.fluid_models = fluid_models(transport)
        self.black_oil_tables = black_oil_tables(transport)
        self.reports = reports(transport)


__all__ = ["WhitsonPVTClient"]

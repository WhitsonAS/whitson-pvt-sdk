from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from whitson_pvt_sdk.http import HTTPTransport


class _BaseClient:
    _transport: HTTPTransport

    def __init__(self, transport: HTTPTransport, resources: Any) -> None:
        self._transport = transport
        self.regions = resources.Regions(transport)
        self.wells = resources.Wells(transport)
        self.samples = resources.Samples(transport)
        self.projects = resources.Projects(transport)
        self.fluid_models = resources.FluidModels(transport)
        self.black_oil_tables = resources.BlackOilTables(transport)
        self.reports = resources.Reports(transport)

    def get_access_token(self) -> str:
        return self._transport.get_access_token()

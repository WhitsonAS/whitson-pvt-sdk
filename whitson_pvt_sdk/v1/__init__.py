from __future__ import annotations

from typing import TYPE_CHECKING

from whitson_pvt_sdk.v1 import resources

if TYPE_CHECKING:
    from whitson_pvt_sdk.http import HTTPTransport


class WhitsonPVTClientV1:
    regions: resources.Regions
    wells: resources.Wells
    samples: resources.Samples
    projects: resources.Projects
    fluid_models: resources.FluidModels
    black_oil_tables: resources.BlackOilTables
    reports: resources.Reports

    def __init__(self, transport: HTTPTransport) -> None:
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


__all__ = ["WhitsonPVTClientV1"]

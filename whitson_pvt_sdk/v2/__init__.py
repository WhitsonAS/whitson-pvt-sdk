from typing import TYPE_CHECKING

from whitson_pvt_sdk._client import _BaseClient
from whitson_pvt_sdk.v2 import resources

if TYPE_CHECKING:
    from whitson_pvt_sdk.http import HTTPTransport


class WhitsonPVTClientV2(_BaseClient):
    regions: resources.Regions
    wells: resources.Wells
    samples: resources.Samples
    projects: resources.Projects
    fluid_models: resources.FluidModels
    black_oil_tables: resources.BlackOilTables
    reports: resources.Reports
    calculations: resources.Calculations

    def __init__(self, transport: "HTTPTransport") -> None:
        super().__init__(transport, resources)
        self.calculations = resources.Calculations(transport)


__all__ = ["WhitsonPVTClientV2"]

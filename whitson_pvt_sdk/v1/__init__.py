from typing import TYPE_CHECKING

from whitson_pvt_sdk._client import _BaseClient
from whitson_pvt_sdk.v1 import resources

if TYPE_CHECKING:
    from whitson_pvt_sdk.http import HTTPTransport


class WhitsonPVTClientV1(_BaseClient):
    regions: resources.Regions
    wells: resources.Wells
    samples: resources.Samples
    projects: resources.Projects
    fluid_models: resources.FluidModels
    black_oil_tables: resources.BlackOilTables
    reports: resources.Reports

    def __init__(self, transport: "HTTPTransport") -> None:
        super().__init__(transport, resources)


__all__ = ["WhitsonPVTClientV1"]

from whitson_pvt_sdk._generated.v1 import resources
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
        self.regions = resources.Regions(transport)
        self.wells = resources.Wells(transport)
        self.samples = resources.Samples(transport)
        self.projects = resources.Projects(transport)
        self.fluid_models = resources.FluidModels(transport)
        self.black_oil_tables = resources.BlackOilTables(transport)
        self.reports = resources.Reports(transport)


__all__ = ["WhitsonPVTClientV1"]

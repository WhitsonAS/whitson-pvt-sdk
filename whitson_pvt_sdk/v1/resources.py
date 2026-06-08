from whitson_pvt_sdk._generated.v1 import resources as generated_resources
from whitson_pvt_sdk.v1.models import GetSampleListModel

BlackOilTables = generated_resources.BlackOilTables
FluidModels = generated_resources.FluidModels
Projects = generated_resources.Projects
Regions = generated_resources.Regions
Reports = generated_resources.Reports
Wells = generated_resources.Wells


class Samples(generated_resources.Samples):
    def list(self, well_id: int) -> GetSampleListModel:
        body = self._transport.get(f"/wells/{well_id}")
        return GetSampleListModel.model_validate(body)


__all__ = (
    "BlackOilTables",
    "FluidModels",
    "Projects",
    "Regions",
    "Reports",
    "Samples",
    "Wells",
)

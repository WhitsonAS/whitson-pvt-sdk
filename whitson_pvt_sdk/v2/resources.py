from whitson_pvt_sdk._generated.v2 import resources as generated_resources
from whitson_pvt_sdk.shared.models import CompositionSource
from whitson_pvt_sdk.v2._helpers import calculations as calculation_helpers
from whitson_pvt_sdk.v2.models import (
    CalculationCompositionEntryModel,
    GetSampleListModel,
    SampleToEosSlateConversionCalculationRequestModel,
)

BlackOilTables = generated_resources.BlackOilTables
FluidModels = generated_resources.FluidModels
Projects = generated_resources.Projects
Regions = generated_resources.Regions
Reports = generated_resources.Reports
Wells = generated_resources.Wells


class Calculations(generated_resources.Calculations):
    def get_sample_feed_compositions(
        self,
        fluid_model_id: int,
        sample_ids: list[int],
        source: CompositionSource = "slate_to_slate_converted",
    ) -> dict[int, list[CalculationCompositionEntryModel]]:
        if source == "slate_to_slate_converted":
            response = self.calculate_sample_to_eos_slate_conversion(
                SampleToEosSlateConversionCalculationRequestModel(
                    fluid_model_id=fluid_model_id,
                    sample_ids=sample_ids,
                )
            )
            return calculation_helpers.slate_to_slate_converted_feed_compositions(
                response, sample_ids
            )

        return calculation_helpers.adjusted_feed_compositions(
            self._transport, fluid_model_id, sample_ids
        )

    def get_sample_feed_composition(
        self,
        fluid_model_id: int,
        sample_id: int,
        source: CompositionSource = "slate_to_slate_converted",
    ) -> list[CalculationCompositionEntryModel]:
        return self.get_sample_feed_compositions(
            fluid_model_id=fluid_model_id,
            sample_ids=[sample_id],
            source=source,
        )[sample_id]


class Samples(generated_resources.Samples):
    def list(self, well_id: int) -> GetSampleListModel:
        body = self._transport.get(f"/wells/{well_id}")
        return GetSampleListModel.model_validate(body)


__all__ = (
    "BlackOilTables",
    "Calculations",
    "FluidModels",
    "Projects",
    "Regions",
    "Reports",
    "Samples",
    "Wells",
)

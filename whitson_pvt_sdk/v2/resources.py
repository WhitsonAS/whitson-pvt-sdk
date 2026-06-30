from typing import Any

from whitson_pvt_sdk._generated.v2 import resources as generated_resources
from whitson_pvt_sdk.shared.models import CompositionSource
from whitson_pvt_sdk.v2._helpers import calculations as calculation_helpers
from whitson_pvt_sdk.v2.models import (
    CalculationCompositionEntryModel,
    GetSampleListModel,
    GorRecombinationCalculationInputModel,
    GorRecombinationCalculationRequestModel,
    SampleToEosSlateConversionCalculationRequestModel,
    SurfaceProcessModel,
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

    def get_gor_recombination_feed_compositions(
        self,
        fluid_model_id: int,
        gor_values: dict[int, float],
        gor_unit: Any,
        recombination_type: Any,
        surface_process: SurfaceProcessModel,
        *,
        remove_mud_components: bool = False,
        feed_compositions: dict[int, list[CalculationCompositionEntryModel]] | None = None,
        source: CompositionSource = "slate_to_slate_converted",
    ) -> dict[int, list[CalculationCompositionEntryModel]]:
        """Run GOR recombination and return feed compositions keyed by sample id.

        When *feed_compositions* is provided the internal conversion is
        skipped and *source* is ignored.
        """
        if feed_compositions is None:
            feed_compositions = self.get_sample_feed_compositions(
                fluid_model_id=fluid_model_id,
                sample_ids=list(gor_values.keys()),
                source=source,
            )
        inputs = [
            GorRecombinationCalculationInputModel(
                feed_composition=feed_compositions[sample_id],
                recombination_gor=gor_value,
            )
            for sample_id, gor_value in gor_values.items()
        ]
        response = self.calculate_gor_recombination(
            GorRecombinationCalculationRequestModel(
                fluid_model_id=fluid_model_id,
                gor_unit=gor_unit,
                inputs=inputs,
                recombination_type=recombination_type,
                remove_mud_components=remove_mud_components,
                surface_process=surface_process,
            )
        )
        return calculation_helpers.gor_recombination_feed_compositions(
            response, list(gor_values.keys())
        )

    def get_gor_recombination_feed_composition(
        self,
        fluid_model_id: int,
        sample_id: int,
        recombination_gor: float,
        gor_unit: Any,
        recombination_type: Any,
        surface_process: SurfaceProcessModel,
        *,
        remove_mud_components: bool = False,
        feed_composition: list[CalculationCompositionEntryModel] | None = None,
        source: CompositionSource = "slate_to_slate_converted",
    ) -> list[CalculationCompositionEntryModel]:
        """Run GOR recombination for a single sample and return its feed composition.

        When *feed_composition* is provided the internal conversion is
        skipped and *source* is ignored.
        """
        feed_compositions: dict[int, list[CalculationCompositionEntryModel]] | None = None
        if feed_composition is not None:
            feed_compositions = {sample_id: feed_composition}
        return self.get_gor_recombination_feed_compositions(
            fluid_model_id=fluid_model_id,
            gor_values={sample_id: recombination_gor},
            gor_unit=gor_unit,
            recombination_type=recombination_type,
            surface_process=surface_process,
            remove_mud_components=remove_mud_components,
            feed_compositions=feed_compositions,
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

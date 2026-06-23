from whitson_pvt_sdk._generated.v2 import resources as generated_resources
from whitson_pvt_sdk.shared.models import (
    CompositionSource,
    FlashType,
    OutputUnitSystem,
    PressureUnit,
    SampleFlashInput,
    TemperatureUnit,
)
from whitson_pvt_sdk.v2._helpers import calculations as calculation_helpers
from whitson_pvt_sdk.v2.models import (
    CalculationCompositionEntryModel,
    FlashCalculationInputModel,
    FlashCalculationRequestModel,
    FlashCalculationResponseModel,
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
    def calculate_flash_for_samples(
        self,
        fluid_model_id: int,
        inputs: list[SampleFlashInput],
        pressure_unit: PressureUnit,
        temperature_unit: TemperatureUnit,
        source: CompositionSource = "slate_to_slate_converted",
        flash_type: FlashType = "positive",
        output_unit_system: OutputUnitSystem = "SI",
    ) -> FlashCalculationResponseModel:
        sample_ids = [sample_input.sample_id for sample_input in inputs]
        feed_compositions = self.get_sample_feed_compositions(
            fluid_model_id=fluid_model_id,
            sample_ids=sample_ids,
            source=source,
        )

        return self.calculate_flash(
            FlashCalculationRequestModel(
                fluid_model_id=fluid_model_id,
                inputs=[
                    FlashCalculationInputModel(
                        feed_composition=feed_composition,
                        pressure=sample_input.pressure,
                        temperature=sample_input.temperature,
                    )
                    for sample_input, feed_composition in zip(
                        inputs, feed_compositions, strict=True
                    )
                ],
                pressure_unit=pressure_unit,
                temperature_unit=temperature_unit,
                flash_type=flash_type,
                output_unit_system=output_unit_system,
            )
        )

    def get_sample_feed_compositions(
        self,
        fluid_model_id: int,
        sample_ids: list[int],
        source: CompositionSource = "slate_to_slate_converted",
    ) -> list[list[CalculationCompositionEntryModel]]:
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

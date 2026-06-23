from whitson_pvt_sdk._generated.v2 import fluid_models
from whitson_pvt_sdk.errors import CalculationError
from whitson_pvt_sdk.http import HTTPTransport
from whitson_pvt_sdk.v2.models import (
    CalculationCompositionEntryModel,
    CalculationErrorResultModel,
    SampleToEosSlateConversionCalculationResponseModel,
)


def slate_to_slate_converted_feed_compositions(
    response: SampleToEosSlateConversionCalculationResponseModel,
    sample_ids: list[int],
) -> list[list[CalculationCompositionEntryModel]]:
    feed_compositions: list[list[CalculationCompositionEntryModel]] = []
    for input_index, (sample_id, result) in enumerate(
        zip(sample_ids, response.results, strict=True)
    ):
        if isinstance(result, CalculationErrorResultModel):
            raise CalculationError(
                result.error.message,
                code=result.error.code,
                sample_id=sample_id,
                input_index=input_index,
                error=result.error,
            )

        component_names = result.result.component_names
        mole_fractions = result.result.mole_fractions

        feed_compositions.append(
            [
                CalculationCompositionEntryModel(
                    component_name=component_name,
                    molar_amount=mole_fraction,
                )
                for component_name, mole_fraction in zip(component_names, mole_fractions)
            ]
        )

    return feed_compositions


def adjusted_feed_compositions(
    transport: HTTPTransport,
    fluid_model_id: int,
    sample_ids: list[int],
) -> list[list[CalculationCompositionEntryModel]]:
    fluid_model = fluid_models.get_fluid_model(transport, fluid_model_id)
    compositions_by_sample_id = {
        composition.sample_id: composition
        for composition in fluid_model.adjusted_compositions
        if composition.sample_id is not None
    }
    missing_sample_ids = [
        sample_id for sample_id in sample_ids if sample_id not in compositions_by_sample_id
    ]
    if missing_sample_ids:
        raise ValueError(
            "Missing adjusted compositions for sample ids: "
            + ", ".join(str(sample_id) for sample_id in missing_sample_ids)
        )

    return [
        [
            CalculationCompositionEntryModel(
                component_name=component.component_name,
                molar_amount=component.molar_amount,
            )
            for component in compositions_by_sample_id[sample_id].components
        ]
        for sample_id in sample_ids
    ]

from whitson_pvt_sdk.errors import CalculationError
from whitson_pvt_sdk.http import HTTPTransport
from whitson_pvt_sdk.v2.models import (
    CalculationCompositionEntryModel,
    CalculationErrorResultModel,
    GetFluidModelModel,
    SampleToEosSlateConversionCalculationResponseModel,
)


def slate_to_slate_converted_feed_compositions(
    response: SampleToEosSlateConversionCalculationResponseModel,
    sample_ids: list[int],
) -> dict[int, list[CalculationCompositionEntryModel]]:
    feed_compositions: dict[int, list[CalculationCompositionEntryModel]] = {}
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

        feed_compositions[sample_id] = result.result.composition

    return feed_compositions


def adjusted_feed_compositions(
    transport: HTTPTransport,
    fluid_model_id: int,
    sample_ids: list[int],
) -> dict[int, list[CalculationCompositionEntryModel]]:
    body = transport.get(f"/fluid-models/{fluid_model_id}")
    fluid_model = GetFluidModelModel.model_validate(body)
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

    return {
        sample_id: [
            CalculationCompositionEntryModel(
                component_name=component.component_name,
                molar_amount=component.molar_amount,
            )
            for component in compositions_by_sample_id[sample_id].components
        ]
        for sample_id in sample_ids
    }

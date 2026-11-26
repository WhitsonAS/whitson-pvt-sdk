from collections.abc import Sequence
from typing import TYPE_CHECKING, TypeAlias

from pydantic import TypeAdapter

from whitson_pvt_sdk._generated.v2 import resources as generated_resources
from whitson_pvt_sdk.errors import APIError, AuthError, CalculationError, MissingDataError
from whitson_pvt_sdk.shared.models import CompositionSource, Identity
from whitson_pvt_sdk.v2.models import (
    CalculationCompositionEntryModel,
    CalculationErrorResultModel,
    ExternalCalculationSuccessResultModelExternalGorRecombinationCalculationResultModel,
    ExternalCalculationSuccessResultModelExternalSampleToEosSlateConversionCalculationResultModel,
    GetSampleListModel,
    GetWellModel,
    GorRecombinationCalculationInputModel,
    GorRecombinationCalculationRequestModel,
    GorUnit,
    RecombinationType,
    SampleToEosSlateConversionCalculationRequestModel,
    SurfaceProcessInputModel,
)

BlackOilTables = generated_resources.BlackOilTables
FluidModels = generated_resources.FluidModels
ImportRecords = generated_resources.ImportRecords
ImportSessions = generated_resources.ImportSessions
Projects = generated_resources.Projects
Regions = generated_resources.Regions
Reports = generated_resources.Reports
Wells = generated_resources.Wells

if TYPE_CHECKING:
    from whitson_pvt_sdk.http import HTTPTransport

FeedComposition: TypeAlias = list[CalculationCompositionEntryModel]


_identity: TypeAdapter[Identity] = TypeAdapter(Identity)


class Me:
    def __init__(self, transport: "HTTPTransport") -> None:
        self._transport = transport

    def get(self) -> Identity:
        return _identity.validate_python(self._transport.get("/me"))


class Calculations(generated_resources.Calculations):
    def get_sample_feed_compositions(
        self,
        fluid_model_id: int,
        sample_ids: list[int],
        source: CompositionSource = "slate_to_slate_converted",
    ) -> dict[int, FeedComposition]:
        """Return feed compositions for the given samples keyed by sample id.

        *source* controls where compositions are drawn from:
        ``"slate_to_slate_converted"`` runs a conversion calculation;
        ``"adjusted_compositions"`` reads from the fluid model's
        adjusted compositions.
        """
        match source:
            case "slate_to_slate_converted":
                response = self.calculate_sample_to_eos_slate_conversion(
                    SampleToEosSlateConversionCalculationRequestModel(
                        fluid_model_id=fluid_model_id,
                        sample_ids=sample_ids,
                    )
                )
                return _feed_compositions(sample_ids, response.results)
            case "adjusted_compositions":
                return self._adjusted_feed_compositions(fluid_model_id, sample_ids)

    def get_sample_feed_composition(
        self,
        fluid_model_id: int,
        sample_id: int,
        source: CompositionSource = "slate_to_slate_converted",
    ) -> FeedComposition:
        """Return feed composition for a single sample. See
        :meth:`get_sample_feed_compositions`.
        """
        return self.get_sample_feed_compositions(
            fluid_model_id=fluid_model_id,
            sample_ids=[sample_id],
            source=source,
        )[sample_id]

    def get_gor_recombination_feed_compositions(
        self,
        fluid_model_id: int,
        gor_values: dict[int, float],
        gor_unit: GorUnit,
        recombination_type: RecombinationType,
        surface_process: SurfaceProcessInputModel,
        *,
        remove_mud_components: bool = False,
        source: CompositionSource | dict[int, FeedComposition] = "slate_to_slate_converted",
    ) -> dict[int, FeedComposition]:
        """Run GOR recombination and return feed compositions keyed by sample id.

        *source* is either a :data:`CompositionSource` to draw the input feed
        compositions from, or the feed compositions themselves keyed by sample id.
        """
        sample_ids = list(gor_values)
        match source:
            case dict():
                missing_sample_ids = [
                    sample_id for sample_id in sample_ids if sample_id not in source
                ]
                if missing_sample_ids:
                    raise MissingDataError(
                        "source has no feed composition for sample ids: "
                        + ", ".join(str(sample_id) for sample_id in missing_sample_ids)
                    )
                feed_compositions = source
            case _:
                feed_compositions = self.get_sample_feed_compositions(
                    fluid_model_id=fluid_model_id, sample_ids=sample_ids, source=source
                )
        response = self.calculate_gor_recombination(
            GorRecombinationCalculationRequestModel(
                fluid_model_id=fluid_model_id,
                gor_unit=gor_unit,
                inputs=[
                    GorRecombinationCalculationInputModel(
                        feed_composition=feed_compositions[sample_id],
                        recombination_gor=gor_value,
                    )
                    for sample_id, gor_value in gor_values.items()
                ],
                recombination_type=recombination_type,
                remove_mud_components=remove_mud_components,
                surface_process=surface_process,
            )
        )
        return _feed_compositions(sample_ids, response.results)

    def get_gor_recombination_feed_composition(
        self,
        fluid_model_id: int,
        sample_id: int,
        recombination_gor: float,
        gor_unit: GorUnit,
        recombination_type: RecombinationType,
        surface_process: SurfaceProcessInputModel,
        *,
        remove_mud_components: bool = False,
        source: CompositionSource | FeedComposition = "slate_to_slate_converted",
    ) -> FeedComposition:
        """Run GOR recombination for a single sample and return its feed composition.

        *source* is either a :data:`CompositionSource` or the sample's feed
        composition itself.
        """
        return self.get_gor_recombination_feed_compositions(
            fluid_model_id=fluid_model_id,
            gor_values={sample_id: recombination_gor},
            gor_unit=gor_unit,
            recombination_type=recombination_type,
            surface_process=surface_process,
            remove_mud_components=remove_mud_components,
            source={sample_id: source} if isinstance(source, list) else source,
        )[sample_id]

    def _adjusted_feed_compositions(
        self, fluid_model_id: int, sample_ids: list[int]
    ) -> dict[int, FeedComposition]:
        fluid_model = generated_resources.FluidModels(self._transport).get(fluid_model_id)
        if fluid_model.adjusted_compositions is None:
            raise AuthError(
                f"Fluid model {fluid_model_id} was returned without its adjusted compositions: "
                "this credential may not read samples (it needs the samples:read scope).",
                403,
            )
        compositions_by_sample_id = {
            composition.sample_id: composition
            for composition in fluid_model.adjusted_compositions
            if composition.sample_id is not None
        }
        missing_sample_ids = [
            sample_id for sample_id in sample_ids if sample_id not in compositions_by_sample_id
        ]
        if missing_sample_ids:
            raise MissingDataError(
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


_CompositionResult: TypeAlias = (
    CalculationErrorResultModel
    | ExternalCalculationSuccessResultModelExternalSampleToEosSlateConversionCalculationResultModel
    | ExternalCalculationSuccessResultModelExternalGorRecombinationCalculationResultModel
)


def _feed_compositions(
    sample_ids: list[int], results: Sequence[_CompositionResult]
) -> dict[int, FeedComposition]:
    if len(results) != len(sample_ids):
        raise APIError(
            f"The server returned {len(results)} result{'' if len(results) == 1 else 's'} "
            f"for {len(sample_ids)} samples.",
            200,
        )
    feed_compositions: dict[int, FeedComposition] = {}
    for input_index, (sample_id, result) in enumerate(zip(sample_ids, results, strict=True)):
        match result:
            case CalculationErrorResultModel(error=error):
                raise CalculationError(
                    error.message,
                    code=error.code,
                    sample_id=sample_id,
                    input_index=input_index,
                    error=error,
                )
            case _:
                feed_compositions[sample_id] = result.result.composition
    return feed_compositions


class Samples(generated_resources.Samples):
    def list(self, well_id: int) -> GetSampleListModel:
        well = GetWellModel.model_validate(self._transport.get(f"/wells/{well_id}"))
        if well.samples is None:
            raise AuthError(
                f"Well {well_id} was returned without its samples: this credential may not read "
                "samples (it needs the samples:read scope).",
                403,
            )
        return GetSampleListModel(samples=well.samples)


__all__ = (
    "BlackOilTables",
    "Calculations",
    "FluidModels",
    "ImportRecords",
    "ImportSessions",
    "Me",
    "Projects",
    "Regions",
    "Reports",
    "Samples",
    "Wells",
)

from ...http import HTTPTransport
from ...v2.models import (
    FlashCalculationRequestModel,
    FlashCalculationResponseModel,
    GorRecombinationCalculationRequestModel,
    GorRecombinationCalculationResponseModel,
    PhaseEnvelopeCalculationRequestModel,
    PhaseEnvelopeCalculationResponseModel,
    SampleToEosSlateConversionCalculationRequestModel,
    SampleToEosSlateConversionCalculationResponseModel,
    SaturationPressureCalculationRequestModel,
    SaturationPressureCalculationResponseModel,
    SeparatorProcessCalculationRequestModel,
    SeparatorProcessCalculationResponseModel,
)


def calculate_flash(
    transport: HTTPTransport, data: FlashCalculationRequestModel
) -> FlashCalculationResponseModel:
    body = transport.post("/calculations/flash", body=data.model_dump(exclude_unset=True))
    return FlashCalculationResponseModel.model_validate(body)


def calculate_gor_recombination(
    transport: HTTPTransport, data: GorRecombinationCalculationRequestModel
) -> GorRecombinationCalculationResponseModel:
    body = transport.post(
        "/calculations/gor-recombination", body=data.model_dump(exclude_unset=True)
    )
    return GorRecombinationCalculationResponseModel.model_validate(body)


def calculate_phase_envelope(
    transport: HTTPTransport, data: PhaseEnvelopeCalculationRequestModel
) -> PhaseEnvelopeCalculationResponseModel:
    body = transport.post("/calculations/phase-envelope", body=data.model_dump(exclude_unset=True))
    return PhaseEnvelopeCalculationResponseModel.model_validate(body)


def calculate_sample_to_eos_slate_conversion(
    transport: HTTPTransport, data: SampleToEosSlateConversionCalculationRequestModel
) -> SampleToEosSlateConversionCalculationResponseModel:
    body = transport.post(
        "/calculations/sample-to-eos-slate-conversion", body=data.model_dump(exclude_unset=True)
    )
    return SampleToEosSlateConversionCalculationResponseModel.model_validate(body)


def calculate_saturation_pressure(
    transport: HTTPTransport, data: SaturationPressureCalculationRequestModel
) -> SaturationPressureCalculationResponseModel:
    body = transport.post(
        "/calculations/saturation-pressure", body=data.model_dump(exclude_unset=True)
    )
    return SaturationPressureCalculationResponseModel.model_validate(body)


def calculate_separator_process(
    transport: HTTPTransport, data: SeparatorProcessCalculationRequestModel
) -> SeparatorProcessCalculationResponseModel:
    body = transport.post(
        "/calculations/separator-process", body=data.model_dump(exclude_unset=True)
    )
    return SeparatorProcessCalculationResponseModel.model_validate(body)

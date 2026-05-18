from ..http import HTTPTransport
from ..models.v2._generated import (
    FlashCalculationRequestModel,
    FlashCalculationResponseModel,
    PhaseEnvelopeCalculationRequestModel,
    PhaseEnvelopeCalculationResponseModel,
    SaturationPressureCalculationRequestModel,
    SaturationPressureCalculationResponseModel,
)


def run_flash(
    transport: HTTPTransport, data: FlashCalculationRequestModel
) -> FlashCalculationResponseModel:
    body = transport.post("/calculations/flash", body=data.model_dump(exclude_unset=True))
    return FlashCalculationResponseModel.model_validate(body)


def run_saturation_pressure(
    transport: HTTPTransport, data: SaturationPressureCalculationRequestModel
) -> SaturationPressureCalculationResponseModel:
    body = transport.post(
        "/calculations/saturation-pressure", body=data.model_dump(exclude_unset=True)
    )
    return SaturationPressureCalculationResponseModel.model_validate(body)


def run_phase_envelope(
    transport: HTTPTransport, data: PhaseEnvelopeCalculationRequestModel
) -> PhaseEnvelopeCalculationResponseModel:
    body = transport.post("/calculations/phase-envelope", body=data.model_dump(exclude_unset=True))
    return PhaseEnvelopeCalculationResponseModel.model_validate(body)

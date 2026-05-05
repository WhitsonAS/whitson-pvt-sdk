from .._models import (
    ExternalCreateSampleListModel,
    ExternalCreateSampleModel,
    ExternalGetSampleListModel,
    ExternalGetSampleModel,
    ExternalUpdateSampleListModel,
    ExternalUpdateSampleModel,
)
from ..http import HTTPTransport


def list_samples(transport: HTTPTransport, well_id: int) -> ExternalGetSampleListModel:
    body = transport.get(f"/wells/{well_id}")
    return ExternalGetSampleListModel.model_validate(body)


def get_sample(transport: HTTPTransport, sample_id: int) -> ExternalGetSampleModel:
    body = transport.get(f"/samples/{sample_id}")
    return ExternalGetSampleModel.model_validate(body)


def create_sample(
    transport: HTTPTransport, data: ExternalCreateSampleModel
) -> ExternalGetSampleModel:
    body = transport.post("/samples", body=data.model_dump(exclude_unset=True))
    return ExternalGetSampleModel.model_validate(body)


def create_samples_bulk(
    transport: HTTPTransport, data: ExternalCreateSampleListModel
) -> ExternalGetSampleListModel:
    body = transport.post(
        "/samples/bulk",
        body=[model.model_dump(exclude_unset=True) for model in data.root],
    )
    return ExternalGetSampleListModel.model_validate(body)


def update_sample(
    transport: HTTPTransport, sample_id: int, data: ExternalUpdateSampleModel
) -> ExternalGetSampleModel:
    body = transport.put(f"/samples/{sample_id}", body=data.model_dump(exclude_unset=True))
    return ExternalGetSampleModel.model_validate(body)


def update_samples_bulk(
    transport: HTTPTransport, data: ExternalUpdateSampleListModel
) -> ExternalGetSampleListModel:
    body = transport.put(
        "/samples/bulk",
        body=[s.model_dump(exclude_unset=True) for s in data.root],
    )
    return ExternalGetSampleListModel.model_validate(body)


def get_sample_experiment_types(transport: HTTPTransport, sample_id: int) -> list[str]:
    body = transport.get(f"/samples/{sample_id}")
    experiments = body.get("experiments", [])
    return sorted({e.get("type", "Unknown") for e in experiments})

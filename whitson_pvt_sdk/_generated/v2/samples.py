from ...http import HTTPTransport
from ...v2.models import (
    CreateSampleListModel,
    CreateSampleModel,
    GetSampleListModel,
    GetSampleModel,
    UpdateSampleListModel,
    UpdateSampleModel,
)


def list_samples(transport: HTTPTransport, well_id: int) -> GetSampleListModel:
    body = transport.get(f"/wells/{well_id}")
    return GetSampleListModel.model_validate(body)


def get_sample(transport: HTTPTransport, sample_id: int) -> GetSampleModel:
    body = transport.get(f"/samples/{sample_id}")
    return GetSampleModel.model_validate(body)


def create_sample(transport: HTTPTransport, data: CreateSampleModel) -> GetSampleModel:
    body = transport.post("/samples", body=data.model_dump(exclude_unset=True))
    return GetSampleModel.model_validate(body)


def create_samples_bulk(
    transport: HTTPTransport, data: CreateSampleListModel
) -> GetSampleListModel:
    body = transport.post(
        "/samples/bulk",
        body=[model.model_dump(exclude_unset=True) for model in data.root],
    )
    return GetSampleListModel.model_validate(body)


def update_sample(
    transport: HTTPTransport, sample_id: int, data: UpdateSampleModel
) -> GetSampleModel:
    body = transport.put(f"/samples/{sample_id}", body=data.model_dump(exclude_unset=True))
    return GetSampleModel.model_validate(body)


def update_samples_bulk(
    transport: HTTPTransport, data: UpdateSampleListModel
) -> GetSampleListModel:
    body = transport.put(
        "/samples/bulk",
        body=[s.model_dump(exclude_unset=True) for s in data.root],
    )
    return GetSampleListModel.model_validate(body)


def get_sample_experiment_types(transport: HTTPTransport, sample_id: int) -> list[str]:
    body = transport.get(f"/samples/{sample_id}")
    experiments = body.get("experiments", [])
    return sorted({e.get("type", "Unknown") for e in experiments})

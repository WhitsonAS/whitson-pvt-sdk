from ...http import HTTPTransport
from ...v2.models import (
    CreateSampleListModel,
    CreateSampleModel,
    GetSampleListModel,
    GetSampleModel,
    UpdateSampleListModel,
    UpdateSampleModel,
)


def create_sample(transport: HTTPTransport, data: CreateSampleModel) -> GetSampleModel:
    body = transport.post("/samples", body=data.model_dump(exclude_unset=True))
    return GetSampleModel.model_validate(body)


def create_samples(transport: HTTPTransport, data: CreateSampleListModel) -> GetSampleListModel:
    body = transport.post(
        "/samples/bulk", body=[model.model_dump(exclude_unset=True) for model in data.root]
    )
    return GetSampleListModel.model_validate(body)


def update_samples(transport: HTTPTransport, data: UpdateSampleListModel) -> GetSampleListModel:
    body = transport.put(
        "/samples/bulk", body=[model.model_dump(exclude_unset=True) for model in data.root]
    )
    return GetSampleListModel.model_validate(body)


def get_sample(transport: HTTPTransport, sample_id: int) -> GetSampleModel:
    body = transport.get(f"/samples/{sample_id}")
    return GetSampleModel.model_validate(body)


def update_sample(
    transport: HTTPTransport, sample_id: int, data: UpdateSampleModel
) -> GetSampleModel:
    body = transport.put(f"/samples/{sample_id}", body=data.model_dump(exclude_unset=True))
    return GetSampleModel.model_validate(body)

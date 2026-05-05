from ..models import (
    ExternalCreateWellModel,
    ExternalGetWellModel,
    ExternalUpdateWellModel,
    ExternalUpdateWellsListModel,
    ExternalWellsListModel,
)
from ..http import HTTPTransport


def list_wells(transport: HTTPTransport, region_id: int) -> ExternalWellsListModel:
    body = transport.get(f"/regions/{region_id}/wells")
    return ExternalWellsListModel.model_validate(body)


def get_well(transport: HTTPTransport, well_id: int) -> ExternalGetWellModel:
    body = transport.get(f"/wells/{well_id}")
    return ExternalGetWellModel.model_validate(body)


def create_well(transport: HTTPTransport, data: ExternalCreateWellModel) -> ExternalGetWellModel:
    body = transport.post("/wells", body=data.model_dump(exclude={"samples"}, exclude_unset=True))
    return ExternalGetWellModel.model_validate(body)


def update_well(
    transport: HTTPTransport, well_id: int, data: ExternalUpdateWellModel
) -> ExternalGetWellModel:
    body = transport.put(f"/wells/{well_id}", body=data.model_dump(exclude_unset=True))
    return ExternalGetWellModel.model_validate(body)


def update_wells_bulk(
    transport: HTTPTransport, data: ExternalUpdateWellsListModel
) -> ExternalWellsListModel:
    body = transport.put("/wells/bulk", body=[w.model_dump(exclude_unset=True) for w in data.root])
    return ExternalWellsListModel.model_validate(body)

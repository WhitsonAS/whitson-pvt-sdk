from ...http import HTTPTransport
from ...models.v1 import (
    CreateWellModel,
    GetWellModel,
    UpdateWellModel,
    UpdateWellsListModel,
    WellsListModel,
)


def list_wells(transport: HTTPTransport, region_id: int) -> WellsListModel:
    body = transport.get(f"/regions/{region_id}/wells")
    return WellsListModel.model_validate(body)


def get_well(transport: HTTPTransport, well_id: int) -> GetWellModel:
    body = transport.get(f"/wells/{well_id}")
    return GetWellModel.model_validate(body)


def create_well(transport: HTTPTransport, data: CreateWellModel) -> GetWellModel:
    body = transport.post("/wells", body=data.model_dump(exclude={"samples"}, exclude_unset=True))
    return GetWellModel.model_validate(body)


def update_well(transport: HTTPTransport, well_id: int, data: UpdateWellModel) -> GetWellModel:
    body = transport.put(f"/wells/{well_id}", body=data.model_dump(exclude_unset=True))
    return GetWellModel.model_validate(body)


def update_wells_bulk(transport: HTTPTransport, data: UpdateWellsListModel) -> WellsListModel:
    body = transport.put("/wells/bulk", body=[w.model_dump(exclude_unset=True) for w in data.root])
    return WellsListModel.model_validate(body)

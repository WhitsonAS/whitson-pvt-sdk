from ...http import HTTPTransport
from ...shared.models import PaginationParams
from ...v2.models import (
    CreateWellModel,
    GetWellModel,
    PaginatedWellsModel,
    UpdateWellModel,
    UpdateWellsListModel,
    WellsListModel,
)


def list_wells_info(
    transport: HTTPTransport, region_id: int, cursor: str | None = None, limit: int | None = None
) -> PaginatedWellsModel:
    body = transport.get(
        f"/regions/{region_id}/wells",
        params=PaginationParams(cursor=cursor, limit=limit).model_dump(exclude_none=True),
    )
    return PaginatedWellsModel.model_validate(body)


def create_well(transport: HTTPTransport, data: CreateWellModel) -> GetWellModel:
    body = transport.post("/wells", body=data.model_dump(exclude={"samples"}, exclude_unset=True))
    return GetWellModel.model_validate(body)


def update_wells(transport: HTTPTransport, data: UpdateWellsListModel) -> WellsListModel:
    body = transport.put(
        "/wells/bulk", body=[model.model_dump(exclude_unset=True) for model in data.root]
    )
    return WellsListModel.model_validate(body)


def get_well(transport: HTTPTransport, well_id: int) -> GetWellModel:
    body = transport.get(f"/wells/{well_id}")
    return GetWellModel.model_validate(body)


def update_well(transport: HTTPTransport, well_id: int, data: UpdateWellModel) -> GetWellModel:
    body = transport.put(f"/wells/{well_id}", body=data.model_dump(exclude_unset=True))
    return GetWellModel.model_validate(body)

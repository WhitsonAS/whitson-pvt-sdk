from ...http import HTTPTransport
from ...shared.models import PaginationParams
from ...v2.models import (
    CreateRegionModel,
    GetRegionModel,
    PaginatedRegionsModel,
    UpdateRegionModel,
)


def list_regions(
    transport: HTTPTransport, cursor: str | None = None, limit: int | None = None
) -> PaginatedRegionsModel:
    body = transport.get(
        "/regions",
        params=PaginationParams(cursor=cursor, limit=limit).model_dump(exclude_none=True),
    )
    return PaginatedRegionsModel.model_validate(body)


def create_region(transport: HTTPTransport, data: CreateRegionModel) -> GetRegionModel:
    body = transport.post("/regions", body=data.model_dump(exclude_unset=True))
    return GetRegionModel.model_validate(body)


def get_region(transport: HTTPTransport, region_id: int) -> GetRegionModel:
    body = transport.get(f"/regions/{region_id}")
    return GetRegionModel.model_validate(body)


def update_region(
    transport: HTTPTransport, region_id: int, data: UpdateRegionModel
) -> GetRegionModel:
    body = transport.put(f"/regions/{region_id}", body=data.model_dump(exclude_unset=True))
    return GetRegionModel.model_validate(body)

from ..http import HTTPTransport
from ..models import (
    ExternalCreateRegionModel,
    ExternalGetRegionModel,
    ExternalRegionsListModel,
    ExternalUpdateRegionModel,
)


def list_regions(transport: HTTPTransport) -> ExternalRegionsListModel:
    body = transport.get("/regions")
    return ExternalRegionsListModel.model_validate(body)


def get_region(transport: HTTPTransport, region_id: int) -> ExternalGetRegionModel:
    body = transport.get(f"/regions/{region_id}")
    return ExternalGetRegionModel.model_validate(body)


def create_region(
    transport: HTTPTransport, data: ExternalCreateRegionModel
) -> ExternalGetRegionModel:
    body = transport.post("/regions", body=data.model_dump(exclude_unset=True))
    return ExternalGetRegionModel.model_validate(body)


def update_region(
    transport: HTTPTransport, region_id: int, data: ExternalUpdateRegionModel
) -> ExternalGetRegionModel:
    body = transport.put(f"/regions/{region_id}", body=data.model_dump(exclude_unset=True))
    return ExternalGetRegionModel.model_validate(body)

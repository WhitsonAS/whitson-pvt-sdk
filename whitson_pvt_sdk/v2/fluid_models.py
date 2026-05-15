from ..http import HTTPTransport
from ..models.v2._generated import (
    GetFluidModelModel,
    PaginatedFluidModelsModel,
)


def list_fluid_models(transport: HTTPTransport, project_id: int) -> PaginatedFluidModelsModel:
    body = transport.get(f"/projects/{project_id}/fluid-models")
    return PaginatedFluidModelsModel.model_validate(body)


def get_fluid_model(transport: HTTPTransport, fluid_model_id: int) -> GetFluidModelModel:
    body = transport.get(f"/fluid-models/{fluid_model_id}")
    return GetFluidModelModel.model_validate(body)

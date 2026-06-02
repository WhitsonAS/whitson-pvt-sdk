from ...http import HTTPTransport
from ...models.manual import PaginationParams
from ...models.v2 import (
    GetFluidModelModel,
    PaginatedFluidModelsModel,
)


def list_fluid_models(
    transport: HTTPTransport, project_id: int, cursor: str | None = None, limit: int | None = None
) -> PaginatedFluidModelsModel:
    params = PaginationParams(cursor=cursor, limit=limit).model_dump(exclude_none=True)
    body = transport.get(f"/projects/{project_id}/fluid-models", params=params)
    return PaginatedFluidModelsModel.model_validate(body)


def get_fluid_model(transport: HTTPTransport, fluid_model_id: int) -> GetFluidModelModel:
    body = transport.get(f"/fluid-models/{fluid_model_id}")
    return GetFluidModelModel.model_validate(body)

from ...http import HTTPTransport
from ...models.manual import PaginationParams
from ...models.v2 import (
    GetProjectWithFluidModelsModel,
    PaginatedProjectsModel,
)


def list_projects(
    transport: HTTPTransport, region_id: int, cursor: str | None = None, limit: int | None = None
) -> PaginatedProjectsModel:
    params = PaginationParams(cursor=cursor, limit=limit).model_dump(exclude_none=True)
    body = transport.get(f"/regions/{region_id}/projects", params=params)
    return PaginatedProjectsModel.model_validate(body)


def get_project(transport: HTTPTransport, project_id: int) -> GetProjectWithFluidModelsModel:
    body = transport.get(f"/projects/{project_id}")
    return GetProjectWithFluidModelsModel.model_validate(body)

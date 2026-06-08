from ...http import HTTPTransport
from ...shared.models import PaginationParams
from ...v2.models import (
    GetProjectWithFluidModelsModel,
    PaginatedProjectsModel,
)


def get_project(transport: HTTPTransport, project_id: int) -> GetProjectWithFluidModelsModel:
    body = transport.get(f"/projects/{project_id}")
    return GetProjectWithFluidModelsModel.model_validate(body)


def list_projects(
    transport: HTTPTransport, region_id: int, cursor: str | None = None, limit: int | None = None
) -> PaginatedProjectsModel:
    body = transport.get(
        f"/regions/{region_id}/projects",
        params=PaginationParams(cursor=cursor, limit=limit).model_dump(exclude_none=True),
    )
    return PaginatedProjectsModel.model_validate(body)

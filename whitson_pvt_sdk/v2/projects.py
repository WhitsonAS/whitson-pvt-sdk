from ..http import HTTPTransport
from ..models.v2._generated import (
    GetProjectWithFluidModelsModel,
    PaginatedProjectsModel,
)


def list_projects(transport: HTTPTransport, region_id: int) -> PaginatedProjectsModel:
    body = transport.get(f"/regions/{region_id}/projects")
    return PaginatedProjectsModel.model_validate(body)


def get_project(transport: HTTPTransport, project_id: int) -> GetProjectWithFluidModelsModel:
    body = transport.get(f"/projects/{project_id}")
    return GetProjectWithFluidModelsModel.model_validate(body)

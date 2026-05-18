from ..http import HTTPTransport
from ..models.v1._generated import (
    GetProjectWithFluidModelsModel,
    ProjectsListModel,
)


def list_projects(transport: HTTPTransport, region_id: int) -> ProjectsListModel:
    body = transport.get(f"/regions/{region_id}/projects")
    return ProjectsListModel.model_validate(body)


def get_project(transport: HTTPTransport, project_id: int) -> GetProjectWithFluidModelsModel:
    body = transport.get(f"/projects/{project_id}")
    return GetProjectWithFluidModelsModel.model_validate(body)

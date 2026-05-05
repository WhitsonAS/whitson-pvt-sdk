from .._models import (
    ExternalGetProjectWithFluidModelsModel,
    ExternalProjectsListModel,
)
from ..http import HTTPTransport


def list_projects(transport: HTTPTransport, region_id: int) -> ExternalProjectsListModel:
    body = transport.get(f"/regions/{region_id}/projects")
    return ExternalProjectsListModel.model_validate(body)


def get_project(
    transport: HTTPTransport, project_id: int
) -> ExternalGetProjectWithFluidModelsModel:
    body = transport.get(f"/projects/{project_id}")
    return ExternalGetProjectWithFluidModelsModel.model_validate(body)

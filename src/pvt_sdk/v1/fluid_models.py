from ..models import (
    ExternalFluidModelsListModel,
    ExternalGetFluidModelModel,
)
from ..http import HTTPTransport


def list_fluid_models(transport: HTTPTransport, project_id: int) -> ExternalFluidModelsListModel:
    body = transport.get(f"/projects/{project_id}/fluid-models")
    return ExternalFluidModelsListModel.model_validate(body)


def get_fluid_model(transport: HTTPTransport, fluid_model_id: int) -> ExternalGetFluidModelModel:
    body = transport.get(f"/fluid-models/{fluid_model_id}")
    return ExternalGetFluidModelModel.model_validate(body)

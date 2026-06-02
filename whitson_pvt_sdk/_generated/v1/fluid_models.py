from ...http import HTTPTransport
from ...models.v1 import (
    FluidModelsListModel,
    GetFluidModelModel,
)


def list_fluid_models(transport: HTTPTransport, project_id: int) -> FluidModelsListModel:
    body = transport.get(f"/projects/{project_id}/fluid-models")
    return FluidModelsListModel.model_validate(body)


def get_fluid_model(transport: HTTPTransport, fluid_model_id: int) -> GetFluidModelModel:
    body = transport.get(f"/fluid-models/{fluid_model_id}")
    return GetFluidModelModel.model_validate(body)

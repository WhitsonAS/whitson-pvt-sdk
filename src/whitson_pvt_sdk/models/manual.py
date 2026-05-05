"""Manually maintained models not captured by OpenAPI generation.

These are typically multipart/form-data request schemas that
datamodel-codegen cannot infer from the OpenAPI spec.
"""

from pydantic import BaseModel, Field


class ExternalImportResolutionModel(BaseModel):
    entity: str
    natural_key_id: str | None = None
    import_parent_natural_key_id: str | None = None
    action: str


class ExternalImportArchiveOptions(BaseModel):
    region_id: int | None = None
    acknowledge_suggestions: bool = False
    resolutions: list[ExternalImportResolutionModel] = Field(default_factory=list)

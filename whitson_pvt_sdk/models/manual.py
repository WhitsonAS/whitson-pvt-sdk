from pydantic import BaseModel, Field


class ClientCredentials(BaseModel):
    client_id: str
    client_secret: str


class PaginationParams(BaseModel):
    cursor: str | None = None
    limit: int | None = Field(default=None, ge=1, le=250)


class TokenData(BaseModel):
    access_token: str
    expires_at: float | None = 0
    expires_in: int
    token_type: str


class ExternalImportResolutionModel(BaseModel):
    entity: str
    natural_key_id: str | None = None
    import_parent_natural_key_id: str | None = None
    action: str


class ExternalImportArchiveOptions(BaseModel):
    region_id: int | None = None
    acknowledge_suggestions: bool = False
    resolutions: list[ExternalImportResolutionModel] = Field(default_factory=list)

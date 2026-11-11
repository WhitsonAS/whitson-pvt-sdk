from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

CompositionSource = Literal["slate_to_slate_converted", "adjusted_compositions"]

HTTPMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]


class RetryConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_attempts: int = Field(default=3, ge=1)
    backoff_factor: float = Field(default=0.25, ge=0)
    max_backoff: float = Field(default=2.0, ge=0)
    statuses: frozenset[int] = frozenset({408, 429, 500, 502, 503, 504})
    methods: frozenset[HTTPMethod] = frozenset({"GET"})


class PaginationParams(BaseModel):
    cursor: str | None = None
    limit: int | None = Field(default=None, ge=1, le=250)


class ImportResolutionModel(BaseModel):
    entity: str
    natural_key_id: str | None = None
    import_parent_natural_key_id: str | None = None
    action: str


class ImportArchiveOptions(BaseModel):
    region_id: int | None = None
    acknowledge_suggestions: bool = False
    resolutions: list[ImportResolutionModel] = Field(default_factory=list)


# Hand-written until GET /external/v2/me is in the OpenAPI document; then replace with the
# generated models.
class _TokenIdentity(BaseModel):
    user_id: int | str
    name: str | None = None
    email: str | None = None
    role: str | None = None
    scopes: list[str] = Field(default_factory=list)


class ApiTokenIdentity(_TokenIdentity):
    kind: Literal["api_token"]


class UserTokenIdentity(_TokenIdentity):
    kind: Literal["user_token"]
    client_id: str | None = None


class LegacyClientIdentity(BaseModel):
    kind: Literal["legacy_client"]
    client_id: str | None = None
    scopes: list[str] = Field(default_factory=list)


Identity = Annotated[
    ApiTokenIdentity | UserTokenIdentity | LegacyClientIdentity, Field(discriminator="kind")
]

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


class ApiResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status_code: int
    headers: dict[str, str]
    content: bytes


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


# Not the generated Caller: role and scopes stay str, so a role or scope added on the server
# does not fail the /me check of `wpvt auth login` in installed SDKs.
class _UserIdentity(BaseModel):
    user_id: int
    name: str | None
    email: str | None
    role: str
    scopes: list[str]


class ApiTokenIdentity(_UserIdentity):
    kind: Literal["api_token"]
    token_id: int
    token_name: str


class UserTokenIdentity(_UserIdentity):
    kind: Literal["user_token"]
    client_id: str | None


class LegacyClientIdentity(BaseModel):
    kind: Literal["legacy_client"]
    client_subject: str | None
    full_access: Literal[True]


Identity = Annotated[
    ApiTokenIdentity | UserTokenIdentity | LegacyClientIdentity, Field(discriminator="kind")
]

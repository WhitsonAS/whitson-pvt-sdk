from pydantic import BaseModel, Field, field_validator, model_validator


class ClientCredentials(BaseModel):
    client_id: str
    client_secret: str


class RetryConfig(BaseModel):
    max_attempts: int = Field(default=3, ge=1)
    backoff_factor: float = Field(default=0.25, ge=0)
    max_backoff: float = Field(default=2.0, ge=0)
    statuses: set[int] = Field(default_factory=lambda: {408, 429, 500, 502, 503, 504})
    methods: set[str] = Field(default_factory=lambda: {"GET"})

    @field_validator("methods")
    @classmethod
    def _uppercase_methods(cls, methods: set[str]) -> set[str]:
        return {method.upper() for method in methods}


class PaginationParams(BaseModel):
    cursor: str | None = None
    limit: int | None = Field(default=None, ge=1, le=250)


class TokenData(BaseModel):
    access_token: str
    expires_at: float | None = 0
    expires_in: int
    token_type: str


class ImportResolutionModel(BaseModel):
    entity: str
    natural_key_id: str | None = None
    import_parent_natural_key_id: str | None = None
    action: str


class ImportArchiveOptions(BaseModel):
    region_id: int | None = None
    acknowledge_suggestions: bool = False
    resolutions: list[ImportResolutionModel] = Field(default_factory=list)


class RegionSpec(BaseModel):
    name: str
    note: str | None = None
    region_type: str | None = "basin"
    reservoir_type: str | None = "Conventional"
    public: bool | None = None


class DomainAuthConfig(BaseModel):
    base_url: str
    client_id: str
    client_secret: str
    auth0_domain: str | None = None
    audience: str | None = None
    version: str = "v2"


class SourceDomainConfig(BaseModel):
    domain: str
    report_ids: list[int] = Field(min_length=1)
    target_region_id: int | None = None
    target_region_name: str | None = None
    acknowledge_suggestions: bool | None = None


class TargetDomainConfig(BaseModel):
    base_url: str
    client_id: str
    client_secret: str
    auth0_domain: str | None = None
    audience: str | None = None
    version: str = "v2"


class MultiDomainCopyConfig(BaseModel):
    domain_configs: dict[str, DomainAuthConfig] = Field(default_factory=dict)
    create_regions: list[RegionSpec] = Field(default_factory=list)
    sources: list[SourceDomainConfig] = Field(min_length=1)
    target: TargetDomainConfig
    target_region_id: int | None = None
    acknowledge_suggestions: bool = False
    max_workers: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _check_duplicate_region_names(self):
        names = [r.name for r in self.create_regions]
        seen: set[str] = set()
        for name in names:
            if name in seen:
                raise ValueError(f"Duplicate region name in create_regions: {name!r}")
            seen.add(name)
        return self

    @model_validator(mode="after")
    def _check_source_domains_exist(self):
        valid = set(self.domain_configs.keys())
        for src in self.sources:
            if src.domain not in valid:
                raise ValueError(f"Unknown domain key: {src.domain!r}")
        return self

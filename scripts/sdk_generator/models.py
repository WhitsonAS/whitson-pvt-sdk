from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Version = Literal["v1", "v2"]
HTTPMethod = Literal["get", "post", "put"]
ParamLocation = Literal["path", "query"]
BodyKind = Literal["none", "model", "root_list", "multipart"]
ReturnKind = Literal["model", "tuple_bytes_filename"]


class EndpointParam(BaseModel):
    name: str
    location: ParamLocation
    python_name: str
    python_type: str
    required: bool = True


class EndpointOverride(BaseModel):
    model_config = ConfigDict(protected_namespaces=("model_validate",))

    resource: str | None = None
    function_name: str | None = None
    public_method_name: str | None = None
    request_model: str | None = None
    response_model: str | None = None
    body_kind: BodyKind | None = None
    return_kind: ReturnKind | None = None
    model_dump_expr: str | None = None
    filename_expr: str | None = None


class Endpoint(BaseModel):
    model_config = ConfigDict(protected_namespaces=("model_validate",))

    version: Version
    resource: str
    function_name: str
    public_method_name: str
    http_method: HTTPMethod
    path: str
    path_params: list[EndpointParam] = Field(default_factory=list)
    query_params: list[EndpointParam] = Field(default_factory=list)
    request_model: str | None = None
    response_model: str | None = None
    body_kind: BodyKind = "none"
    return_kind: ReturnKind = "model"
    model_dump_expr: str | None = None
    filename_expr: str | None = None

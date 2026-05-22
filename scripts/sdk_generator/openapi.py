from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, cast
from urllib.request import urlopen

from sdk_generator.config import HTTP_METHODS, OVERRIDES
from sdk_generator.models import BodyKind, Endpoint, EndpointParam, Version
from sdk_generator.naming import singular, to_snake


def load_openapi(version: str, openapi_path: Path | None, base_url: str) -> dict[str, Any]:
    if openapi_path:
        return json.loads(openapi_path.read_text())

    url = f"{base_url.rstrip('/')}/{version}/docs/openapi.json"
    with urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode())


def parse_endpoints(version: str, spec: dict[str, Any]) -> list[Endpoint]:
    endpoints: list[Endpoint] = []
    for raw_path, path_item in spec.get("paths", {}).items():
        path_params = parse_params(path_item.get("parameters", []))
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            params = [*path_params, *parse_params(operation.get("parameters", []))]
            endpoint = infer_endpoint(version, method, raw_path, operation, params)
            endpoints.append(apply_override(endpoint))
    return endpoints


def infer_endpoint(
    version: str,
    method: str,
    path: str,
    operation: dict[str, Any],
    params: list[EndpointParam],
) -> Endpoint:
    request_model = schema_ref_name(request_schema(operation))
    response_model = schema_ref_name(response_schema(operation))
    body_kind: BodyKind = "none"
    if has_multipart_body(operation):
        body_kind = "multipart"
    elif request_model:
        body_kind = "root_list" if request_model.endswith("ListModel") else "model"

    resource = infer_resource(path, operation)
    function_name = infer_function_name(method, path, resource, operation)

    return Endpoint(
        version=cast(Version, version),
        resource=resource,
        function_name=function_name,
        public_method_name=infer_public_method_name(function_name, resource),
        http_method=cast(Literal["get", "post", "put"], method),
        path=path,
        path_params=[p for p in params if p.location == "path"],
        query_params=[p for p in params if p.location == "query"],
        request_model=request_model,
        response_model=response_model,
        body_kind=body_kind,
    )


def parse_params(raw_params: list[dict[str, Any]]) -> list[EndpointParam]:
    params: list[EndpointParam] = []
    for raw in raw_params:
        if "$ref" in raw:
            continue
        location = raw.get("in")
        if location not in {"path", "query"}:
            continue
        name = raw["name"]
        params.append(
            EndpointParam(
                name=name,
                location=cast(Literal["path", "query"], location),
                python_name=to_snake(name),
                python_type=schema_python_type(raw.get("schema", {})),
                required=bool(raw.get("required", location == "path")),
            )
        )
    return params


def apply_override(endpoint: Endpoint) -> Endpoint:
    version_key = (endpoint.version, endpoint.http_method, endpoint.path)
    wildcard_key = ("*", endpoint.http_method, endpoint.path)
    override = OVERRIDES.get(version_key) or OVERRIDES.get(wildcard_key)
    if not override:
        return endpoint

    data = endpoint.model_dump()
    for key, value in override.model_dump(exclude_none=True).items():
        data[key] = value
    return Endpoint.model_validate(data)


def request_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    request_body = operation.get("requestBody") or {}
    content = request_body.get("content") or {}
    media = content.get("application/json") or next(iter(content.values()), {}) if content else {}
    return media.get("schema")


def response_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    responses = operation.get("responses") or {}
    for status in ("200", "201", "202", "default"):
        response = responses.get(status)
        if not response:
            continue
        content = response.get("content") or {}
        media = (
            content.get("application/json") or next(iter(content.values()), {}) if content else {}
        )
        schema = media.get("schema")
        if schema:
            return schema
    return None


def has_multipart_body(operation: dict[str, Any]) -> bool:
    request_body = operation.get("requestBody") or {}
    return "multipart/form-data" in (request_body.get("content") or {})


def schema_ref_name(schema: dict[str, Any] | None) -> str | None:
    if not schema:
        return None
    if ref := schema.get("$ref"):
        return ref.rsplit("/", 1)[-1]
    if items := schema.get("items"):
        return schema_ref_name(items)
    return None


def schema_python_type(schema: dict[str, Any]) -> str:
    if schema.get("type") == "integer":
        return "int"
    if schema.get("type") == "number":
        return "float"
    if schema.get("type") == "boolean":
        return "bool"
    return "str"


def infer_resource(path: str, operation: dict[str, Any]) -> str:
    tags = operation.get("tags") or []
    if tags:
        return to_snake(tags[0])
    static_parts = [part for part in path.strip("/").split("/") if not part.startswith("{")]
    return to_snake(static_parts[-1] if static_parts else "root")


def infer_function_name(method: str, path: str, resource: str, operation: dict[str, Any]) -> str:
    if operation_id := operation.get("operationId"):
        return to_snake(operation_id)
    if method == "get" and path.endswith(f"/{resource.replace('_', '-')}"):
        return f"list_{resource}"
    if method == "get":
        return f"get_{singular(resource)}"
    if method == "post":
        return f"create_{singular(resource)}"
    if method == "put" and path.endswith("/bulk"):
        return f"update_{resource}_bulk"
    if method == "put":
        return f"update_{singular(resource)}"
    return f"{method}_{resource}"


def infer_public_method_name(function_name: str, resource: str) -> str:
    singular_resource = singular(resource)
    method_names = (
        (f"list_{resource}", "list"),
        (f"get_{singular_resource}", "get"),
        (f"create_{singular_resource}", "create"),
        (f"update_{singular_resource}", "update"),
        (f"create_{resource}_bulk", "create_bulk"),
        (f"update_{resource}_bulk", "update_bulk"),
    )
    for expected, public in method_names:
        if function_name == expected:
            return public
    return function_name

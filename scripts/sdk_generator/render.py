import re
import subprocess
import tempfile
from pathlib import Path

from sdk_generator.config import (
    RESOURCE_CLASS_NAMES,
    ROOT,
)
from sdk_generator.models import Endpoint, EndpointParam
from sdk_generator.naming import sort_resources, to_pascal, to_snake


def format_python(content: str | list[str]) -> str | list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        if isinstance(content, str):
            paths = [Path(tmp) / "generated.py"]
            paths[0].write_text(content)
        else:
            paths = [Path(tmp) / f"{i}.py" for i in range(len(content))]
            for p, c in zip(paths, content):
                p.write_text(c)

        for command in (
            ["uv", "run", "ruff", "check", str(tmp), "--fix", "--select", "I,F401"],
            ["uv", "run", "ruff", "format", str(tmp)],
        ):
            subprocess.run(
                command,
                cwd=ROOT,
                check=True,
                stdout=subprocess.DEVNULL,
            )
        return [p.read_text() for p in paths] if isinstance(content, list) else paths[0].read_text()


def render_module(version: str, resource: str, endpoints: list[Endpoint]) -> str:
    has_multipart = any(endpoint.body_kind == "multipart" for endpoint in endpoints)
    model_imports = sorted(
        {
            model
            for endpoint in endpoints
            for model in (endpoint.request_model, endpoint.response_model)
            if model and model != "ImportArchiveOptions"
        }
    )
    lines = ["from ...http import HTTPTransport\n"]
    if has_multipart:
        lines.insert(0, "from io import BytesIO\n\n")
        lines.append("from ...shared.models import ImportArchiveOptions\n")
    elif needs_pagination(endpoints):
        lines.append("from ...shared.models import PaginationParams\n")
    if model_imports:
        lines.append(f"from ...{version}.models import (\n")
        lines.extend(f"    {name},\n" for name in model_imports)
        lines.append(")\n")
    lines.append("\n")
    lines.extend(render_endpoint(endpoint) for endpoint in endpoints)
    if has_multipart:
        lines.append(render_meta_data_helper())
    return "".join(lines).rstrip() + "\n"


def render_endpoint(endpoint: Endpoint) -> str:
    if endpoint.return_kind == "tuple_bytes_filename":
        return render_bytes_endpoint(endpoint)
    if endpoint.body_kind == "multipart":
        return render_multipart_endpoint(endpoint)

    signature = render_function_signature(endpoint)
    path = render_path(endpoint.path)
    lines = [f"def {endpoint.function_name}({signature}) -> {endpoint.response_model}:\n"]
    call = f"transport.{endpoint.http_method}({path}"
    if endpoint.query_params:
        call += f", params={render_params_expr(endpoint)}"
    if endpoint.body_kind in {"model", "root_list"}:
        call += f", body={render_body_expr(endpoint)}"
    call += ")"
    lines.append(f"    body = {call}\n")
    lines.append(f"    return {endpoint.response_model}.model_validate(body)\n")
    return "".join(lines)


def render_bytes_endpoint(endpoint: Endpoint) -> str:
    signature = render_function_signature(endpoint)
    path = render_path(endpoint.path)
    filename = endpoint.filename_expr or '"download.bin"'
    return (
        f"def {endpoint.function_name}({signature}) -> tuple[bytes, str]:\n"
        f"    data = transport.get_bytes({path})\n"
        f"    filename = {filename}\n"
        "    return data, filename\n"
    )


def render_multipart_endpoint(endpoint: Endpoint) -> str:
    return_model = endpoint.response_model or "dict"
    return (
        f"def {endpoint.function_name}(\n"
        "    transport: HTTPTransport,\n"
        "    archive_data: bytes,\n"
        "    options: ImportArchiveOptions | None = None,\n"
        f") -> {return_model}:\n"
        "    if options is None:\n"
        "        options = ImportArchiveOptions()\n\n"
        "    body = transport.post_multipart(\n"
        f"        {render_path(endpoint.path)},\n"
        '        files={"file": ("archive.zip", BytesIO(archive_data), "application/zip")},\n'
        "        data=_meta_data(options),\n"
        "    )\n"
        f"    return {return_model}.model_validate(body)\n"
    )


def render_function_signature(endpoint: Endpoint) -> str:
    args = ["transport: HTTPTransport"]
    args.extend(f"{param.python_name}: {param.python_type}" for param in endpoint.path_params)
    if endpoint.request_model and endpoint.body_kind in {"model", "root_list"}:
        args.append(f"data: {endpoint.request_model}")
    args.extend(render_query_param(param) for param in endpoint.query_params)
    return ", ".join(args)


def render_query_param(param: EndpointParam) -> str:
    if param.required:
        return f"{param.python_name}: {param.python_type}"
    return f"{param.python_name}: {param.python_type} | None = None"


def render_path(path: str) -> str:
    if "{" not in path:
        return f'"{path}"'
    return 'f"' + re.sub(r"\{([^}]+)\}", lambda m: "{" + to_snake(m.group(1)) + "}", path) + '"'


def render_params_expr(endpoint: Endpoint) -> str:
    names = {param.python_name for param in endpoint.query_params}
    if endpoint.version == "v2" and {"cursor", "limit"}.issubset(names):
        return "PaginationParams(cursor=cursor, limit=limit).model_dump(exclude_none=True)"
    pairs = ", ".join(f'"{param.name}": {param.python_name}' for param in endpoint.query_params)
    return f"{{{pairs}}}"


def render_body_expr(endpoint: Endpoint) -> str:
    if endpoint.model_dump_expr:
        return endpoint.model_dump_expr
    if endpoint.body_kind == "root_list":
        return "[model.model_dump(exclude_unset=True) for model in data.root]"
    return "data.model_dump(exclude_unset=True)"


def render_meta_data_helper() -> str:
    return (
        "def _meta_data(options: ImportArchiveOptions) -> dict | None:\n"
        "    dumped = options.model_dump(exclude_unset=True, exclude_defaults=True)\n"
        "    if not dumped:\n"
        "        return None\n"
        "    return {\n"
        '        "meta_data": options.model_dump_json(\n'
        "            exclude_unset=True, exclude_defaults=True\n"
        "        )\n"
        "    }\n"
    )


def render_resources(version: str, by_resource: dict[str, list[Endpoint]]) -> str:
    resources = sort_resources(by_resource)
    model_imports = sorted(
        {
            model
            for endpoints in by_resource.values()
            for endpoint in endpoints
            for model in (
                endpoint.request_model,
                endpoint.response_model,
                endpoint.pagination_item_model,
            )
            if model
        }
    )
    has_paginated_endpoint = any(
        endpoint.pagination_items_field is not None
        for endpoints in by_resource.values()
        for endpoint in endpoints
    )
    has_multipart = any(
        endpoint.body_kind == "multipart"
        for endpoints in by_resource.values()
        for endpoint in endpoints
    )

    lines = ["from __future__ import annotations\n\n"]
    if has_multipart:
        lines.append("from io import BytesIO\n")
    if has_paginated_endpoint:
        lines.append("from collections.abc import Iterator\n")
    lines.append("from typing import TYPE_CHECKING\n\n")

    if has_paginated_endpoint:
        lines.append("from whitson_pvt_sdk.shared.models import PaginationParams\n")

    lines.append("\nif TYPE_CHECKING:\n")
    lines.append("    from whitson_pvt_sdk.http import HTTPTransport\n")
    if "ImportArchiveOptions" in model_imports and not has_multipart:
        lines.append("    from whitson_pvt_sdk.shared.models import ImportArchiveOptions\n")
    lines.append("\n")

    if has_multipart:
        lines.append("from whitson_pvt_sdk.shared.models import ImportArchiveOptions\n\n")

    # Runtime model imports -- needed by inline model_validate() calls
    generated_models = [model for model in model_imports if model != "ImportArchiveOptions"]
    if generated_models:
        lines.append(f"from whitson_pvt_sdk.{version}.models import (\n")
        lines.extend(f"    {model},\n" for model in generated_models)
        lines.append(")\n")
    if has_paginated_endpoint:
        lines.append("from whitson_pvt_sdk.shared.pagination import Paginator\n")
        lines.append("ListType = list\n\n")
    for resource in resources:
        lines.append(render_resource_class(resource, by_resource[resource]))
    if has_multipart:
        lines.append(render_meta_data_helper())
    return "".join(lines).rstrip() + "\n"


def render_resource_class(resource: str, endpoints: list[Endpoint]) -> str:
    class_name = RESOURCE_CLASS_NAMES.get(resource, to_pascal(resource))
    lines = [
        f"class {class_name}:\n",
        "    _transport: HTTPTransport\n\n",
        "    def __init__(self, transport: HTTPTransport) -> None:\n",
        "        self._transport = transport\n\n",
    ]
    for endpoint in endpoints:
        lines.append(render_resource_method(resource, endpoint))
        if endpoint.pagination_items_field and endpoint.pagination_item_model:
            lines.append(render_resource_pagination_methods(endpoint))
    return "".join(lines)


def render_resource_pagination_methods(endpoint: Endpoint) -> str:
    args = [f"{param.python_name}: {param.python_type}" for param in endpoint.path_params]
    args.extend(render_query_param(param) for param in endpoint.query_params)
    signature_args = f", {', '.join(args)}" if args else ""

    call_parts = [f"{param.python_name}={param.python_name}" for param in endpoint.path_params]
    call_parts.extend(
        f"{param.python_name}={param.python_name}" for param in endpoint.query_params
    )
    paginator_call = ", ".join(call_parts)
    if paginator_call:
        paginator_call = f", {paginator_call}"

    return (
        f"    def iterate(self{signature_args}) -> Iterator[{endpoint.pagination_item_model}]:\n"
        f"        return Paginator.iterate("
        f'self.{endpoint.public_method_name}, "{endpoint.pagination_items_field}"'
        f"{paginator_call})\n\n"
        f"    def list_all(self{signature_args}) -> ListType[{endpoint.pagination_item_model}]:\n"
        f"        return Paginator.list_all("
        f'self.{endpoint.public_method_name}, "{endpoint.pagination_items_field}"'
        f"{paginator_call})\n\n"
    )


def render_resource_method(resource: str, endpoint: Endpoint) -> str:
    if endpoint.return_kind == "tuple_bytes_filename":
        return _render_bytes_resource_method(endpoint)
    if endpoint.body_kind == "multipart":
        return _render_multipart_resource_method(endpoint)
    return _render_inline_resource_method(endpoint)


def _render_bytes_resource_method(endpoint: Endpoint) -> str:
    args = [f"{param.python_name}: {param.python_type}" for param in endpoint.path_params]
    path_expr = render_path(endpoint.path)
    filename = endpoint.filename_expr or '"download.bin"'
    return (
        f"    def {endpoint.public_method_name}(self"
        f"{', ' if args else ''}{', '.join(args)}) -> tuple[bytes, str]:\n"
        f"        data = self._transport.get_bytes({path_expr})\n"
        f"        filename = {filename}\n"
        "        return data, filename\n\n"
    )


def _render_multipart_resource_method(endpoint: Endpoint) -> str:
    return_model = endpoint.response_model or "dict"
    return (
        f"    def {endpoint.public_method_name}(\n"
        "        self, archive_data: bytes, options: ImportArchiveOptions | None = None\n"
        f"    ) -> {return_model}:\n"
        "        if options is None:\n"
        "            options = ImportArchiveOptions()\n\n"
        "        body = self._transport.post_multipart(\n"
        f"            {render_path(endpoint.path)},\n"
        '            files={"file": ("archive.zip", BytesIO(archive_data), "application/zip")},\n'
        "            data=_meta_data(options),\n"
        "        )\n"
        f"        return {return_model}.model_validate(body)\n\n"
    )


def _render_inline_resource_method(endpoint: Endpoint) -> str:
    """Call _transport directly and validate the response."""
    args: list[str] = []
    for param in endpoint.path_params:
        args.append(f"{param.python_name}: {param.python_type}")
    if endpoint.request_model and endpoint.body_kind in {"model", "root_list"}:
        args.append(f"data: {endpoint.request_model}")
    for param in endpoint.query_params:
        args.append(render_query_param(param))

    return_type = endpoint.response_model

    path_expr = render_path(endpoint.path)
    call_parts = [path_expr]
    if endpoint.query_params:
        call_parts.append(f"params={render_params_expr(endpoint)}")
    if endpoint.body_kind in {"model", "root_list"}:
        call_parts.append(f"body={render_body_expr(endpoint)}")

    transport_call = f"self._transport.{endpoint.http_method}({', '.join(call_parts)})"

    return (
        f"    def {endpoint.public_method_name}(self"
        f"{', ' if args else ''}{', '.join(args)}) -> {return_type}:\n"
        f"        body = {transport_call}\n"
        f"        return {endpoint.response_model}.model_validate(body)\n\n"
    )


def needs_pagination(endpoints: list[Endpoint]) -> bool:
    return any(
        endpoint.version == "v2"
        and {"cursor", "limit"}.issubset({param.python_name for param in endpoint.query_params})
        for endpoint in endpoints
    )

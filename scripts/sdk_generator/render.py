from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from sdk_generator.config import (
    EXTRA_MODULE_FUNCTIONS,
    EXTRA_RESOURCE_METHODS,
    RESOURCE_CLASS_NAMES,
    ROOT,
)
from sdk_generator.models import Endpoint, EndpointParam
from sdk_generator.naming import sort_resources, to_pascal, to_snake


def format_python(content: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "generated.py"
        path.write_text(content)
        subprocess.run(
            ["uv", "run", "ruff", "format", str(path)],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        return path.read_text()


def render_module(version: str, resource: str, endpoints: list[Endpoint]) -> str:
    model_imports = sorted(
        {
            model
            for endpoint in endpoints
            for model in (endpoint.request_model, endpoint.response_model)
            if model and model != "ExternalImportArchiveOptions"
        }
    )
    lines = ["from ..http import HTTPTransport\n"]
    if any(endpoint.body_kind == "multipart" for endpoint in endpoints):
        lines.insert(0, "from io import BytesIO\n\n")
        lines.append("from ..models.manual import ExternalImportArchiveOptions\n")
    elif needs_pagination(endpoints):
        lines.append("from ..models.manual import PaginationParams\n")
    if model_imports:
        lines.append(f"from ..models.{version}._generated import (\n")
        lines.extend(f"    {name},\n" for name in model_imports)
        lines.append(")\n")
    lines.append("\n")
    lines.extend(render_endpoint(endpoint) for endpoint in endpoints)
    lines.extend(EXTRA_MODULE_FUNCTIONS.get(version, {}).get(resource, []))
    if any(endpoint.body_kind == "multipart" for endpoint in endpoints):
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
        "    options: ExternalImportArchiveOptions | None = None,\n"
        f") -> {return_model}:\n"
        "    if options is None:\n"
        "        options = ExternalImportArchiveOptions()\n\n"
        "    body = transport.post_multipart(\n"
        f"        {render_path(endpoint.path)},\n"
        "        files={\"file\": (\"archive.zip\", BytesIO(archive_data), \"application/zip\")},\n"
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
        "def _meta_data(options: ExternalImportArchiveOptions) -> dict | None:\n"
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
            for model in (endpoint.request_model, endpoint.response_model)
            if model
        }
    )
    lines = ["from __future__ import annotations\n\n", "from typing import TYPE_CHECKING\n\n"]
    lines.append(f"from whitson_pvt_sdk.{version} import (\n")
    lines.extend(f"    {resource},\n" for resource in resources)
    lines.append(")\n\n")
    lines.append("if TYPE_CHECKING:\n")
    lines.append("    from whitson_pvt_sdk.http import HTTPTransport\n")
    manual_models = [model for model in model_imports if model == "ExternalImportArchiveOptions"]
    generated_models = [model for model in model_imports if model != "ExternalImportArchiveOptions"]
    if manual_models:
        lines.append("    from whitson_pvt_sdk.models.manual import (\n")
        lines.extend(f"        {model},\n" for model in manual_models)
        lines.append("    )\n")
    if generated_models:
        lines.append(f"    from whitson_pvt_sdk.models.{version}._generated import (\n")
        lines.extend(f"        {model},\n" for model in generated_models)
        lines.append("    )\n")
    lines.append("\n")
    for resource in resources:
        lines.append(render_resource_class(resource, by_resource[resource], version))
    return "".join(lines).rstrip() + "\n"


def render_client_init(version: str, by_resource: dict[str, list[Endpoint]]) -> str:
    class_name = f"WhitsonPVTClient{version.upper()}"
    resources = sort_resources(by_resource)
    lines = [
        "from whitson_pvt_sdk.http import HTTPTransport\n",
        f"from whitson_pvt_sdk.{version} import resources\n\n\n",
        f"class {class_name}:\n",
    ]
    for resource in resources:
        class_resource = RESOURCE_CLASS_NAMES.get(resource, to_pascal(resource))
        lines.append(f"    {resource}: resources.{class_resource}\n")
    lines.append("\n")
    lines.append("    def __init__(self, transport: HTTPTransport) -> None:\n")
    for resource in resources:
        class_resource = RESOURCE_CLASS_NAMES.get(resource, to_pascal(resource))
        lines.append(f"        self.{resource} = resources.{class_resource}(transport)\n")
    lines.append("\n\n")
    lines.append(f'__all__ = ["{class_name}"]\n')
    return "".join(lines)


def render_resource_class(resource: str, endpoints: list[Endpoint], version: str) -> str:
    class_name = RESOURCE_CLASS_NAMES.get(resource, to_pascal(resource))
    lines = [
        f"class {class_name}:\n",
        "    def __init__(self, transport: HTTPTransport) -> None:\n",
        "        self._transport = transport\n\n",
    ]
    for endpoint in endpoints:
        lines.append(render_resource_method(resource, endpoint))
    lines.extend(EXTRA_RESOURCE_METHODS.get(version, {}).get(resource, []))
    return "".join(lines)


def render_resource_method(resource: str, endpoint: Endpoint) -> str:
    args = []
    call_args = ["self._transport"]
    if endpoint.body_kind == "multipart":
        args = ["archive_data: bytes", "options: ExternalImportArchiveOptions | None = None"]
        call_args.extend(["archive_data", "options"])
    else:
        for param in endpoint.path_params:
            args.append(f"{param.python_name}: {param.python_type}")
            call_args.append(param.python_name)
        if endpoint.request_model and endpoint.body_kind in {"model", "root_list"}:
            args.append(f"data: {endpoint.request_model}")
            call_args.append("data")
        for param in endpoint.query_params:
            args.append(render_query_param(param))
            call_args.append(param.python_name)

    if endpoint.return_kind == "tuple_bytes_filename":
        return_type = "tuple[bytes, str]"
    else:
        return_type = endpoint.response_model
    return (
        f"    def {endpoint.public_method_name}(self"
        f"{', ' if args else ''}{', '.join(args)}) -> {return_type}:\n"
        f"        return {resource}.{endpoint.function_name}({', '.join(call_args)})\n\n"
    )


def needs_pagination(endpoints: list[Endpoint]) -> bool:
    return any(
        endpoint.version == "v2"
        and {"cursor", "limit"}.issubset({param.python_name for param in endpoint.query_params})
        for endpoint in endpoints
    )

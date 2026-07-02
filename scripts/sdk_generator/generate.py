import argparse
import difflib
import json
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from datamodel_code_generator import GenerateConfig, InputFileType, PythonVersion, generate
from datamodel_code_generator.enums import DataModelType
from datamodel_code_generator.format import Formatter
from datamodel_code_generator.parser import LiteralType

from sdk_generator.config import GENERATED_DIR, SUPPORTED_VERSIONS
from sdk_generator.models import Endpoint
from sdk_generator.openapi import load_openapi, parse_endpoints
from sdk_generator.render import format_python, render_resources

LIST_TYPE_ALIAS_RE = re.compile(
    r'^([A-Za-z_]\w*) = TypeAliasType\("([A-Za-z_]\w*)", (list\[.+\])\)$',
    re.MULTILINE,
)


def main() -> None:
    args = parse_args()
    versions = SUPPORTED_VERSIONS if args.version == "all" else (args.version,)

    for version in versions:
        spec = load_openapi(version, args.openapi, args.base_url)
        if not args.endpoints_only:
            generate_models(
                version,
                spec,
                check=args.check,
                reuse_model=args.reuse_model,
                collapse_reuse_models=args.collapse_reuse_models,
            )
        if not args.models_only:
            generate_endpoints(version, spec, check=args.check)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate whitson PVT SDK models and endpoint wrappers."
    )
    parser.add_argument("version", choices=[*SUPPORTED_VERSIONS, "all"])
    parser.add_argument("--base-url", default="http://localhost:4000/external")
    parser.add_argument(
        "--openapi", type=Path, help="OpenAPI JSON file. Only valid for one version."
    )
    parser.add_argument("--models-only", action="store_true")
    parser.add_argument("--reuse-model", action="store_true")
    parser.add_argument("--collapse-reuse-models", action="store_true")
    parser.add_argument("--endpoints-only", action="store_true")
    parser.add_argument(
        "--check", action="store_true", help="Diff generated output without writing files."
    )
    args = parser.parse_args()
    if args.openapi and args.version == "all":
        parser.error("--openapi can only be used with a single version")
    if args.models_only and args.endpoints_only:
        parser.error("--models-only and --endpoints-only are mutually exclusive")
    return args


def generate_models(
    version: str,
    spec: dict[str, Any],
    *,
    check: bool,
    reuse_model: bool,
    collapse_reuse_models: bool,
) -> None:
    output = GENERATED_DIR / version / "models.py"
    if check:
        with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
            target = Path(tmp) / "models.py"
            generate_model_file(
                version,
                spec,
                target,
                reuse_model=reuse_model,
                collapse_reuse_models=collapse_reuse_models,
            )
            assert_same(output, target.read_text())
    else:
        generate_model_file(
            version,
            spec,
            output,
            reuse_model=reuse_model,
            collapse_reuse_models=collapse_reuse_models,
        )


def generate_model_file(
    version: str,
    spec: dict[str, Any],
    target: Path,
    *,
    reuse_model: bool,
    collapse_reuse_models: bool,
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    config = GenerateConfig(
        input_file_type=InputFileType.OpenAPI,
        input_filename=f"{version}/openapi.json",
        output=target,
        output_model_type=DataModelType.PydanticV2BaseModel,
        target_python_version=PythonVersion.PY_310,
        base_class="pydantic.BaseModel",
        keep_model_order=True,
        collapse_root_models=False,
        use_type_alias=True,
        reuse_model=reuse_model,
        collapse_reuse_models=collapse_reuse_models,
        snake_case_field=True,
        use_field_description=True,
        use_union_operator=True,
        use_standard_collections=True,
        use_standard_primitive_types=True,
        use_annotated=True,
        field_constraints=True,
        enum_field_as_literal=LiteralType.All,
        use_title_as_name=True,
        formatters=[Formatter.RUFF_CHECK, Formatter.RUFF_FORMAT],
        disable_timestamp=True,
    )
    array_root_model_names = find_array_root_model_names(spec)
    generate(json.dumps(strip_schema_titles(spec)), config=config)
    restore_list_root_models(target, array_root_model_names)


def find_array_root_model_names(spec: dict[str, Any]) -> set[str]:
    schemas = spec.get("components", {}).get("schemas", {})
    if not isinstance(schemas, dict):
        return set()
    return {
        name
        for name, schema in schemas.items()
        if isinstance(name, str) and isinstance(schema, dict) and schema.get("type") == "array"
    }


def restore_list_root_models(target: Path, model_names: set[str]) -> None:
    if not model_names:
        return
    content = target.read_text()
    restored = False

    def replace(match: re.Match[str]) -> str:
        nonlocal restored
        replacement = replace_list_type_alias(match, model_names)
        if replacement != match.group(0):
            restored = True
        return replacement

    content = LIST_TYPE_ALIAS_RE.sub(replace, content)
    if not restored:
        return
    target.write_text(ensure_pydantic_import(content, "RootModel"))


def replace_list_type_alias(match: re.Match[str], model_names: set[str]) -> str:
    name = match.group(1)
    alias_name = match.group(2)
    list_type = match.group(3)
    if name != alias_name or name not in model_names:
        return match.group(0)
    return f"class {name}(RootModel[{list_type}]):\n    root: {list_type}"


def ensure_pydantic_import(content: str, import_name: str) -> str:
    lines = content.splitlines()
    for index, line in enumerate(lines):
        prefix = "from pydantic import "
        if not line.startswith(prefix):
            continue
        imports = [name.strip() for name in line.removeprefix(prefix).split(",")]
        if import_name not in imports:
            imports.append(import_name)
            lines[index] = f"{prefix}{', '.join(sorted(imports))}"
        return "\n".join(lines) + "\n"

    insert_at = next(
        (
            index
            for index, line in enumerate(lines)
            if line.startswith("from typing_extensions import ")
        ),
        len(lines),
    )
    lines.insert(insert_at, f"from pydantic import {import_name}")
    return "\n".join(lines) + "\n"


def strip_schema_titles(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: strip_schema_titles(child) for key, child in value.items() if key != "title"}
    if isinstance(value, list):
        return [strip_schema_titles(child) for child in value]
    return value


def generate_endpoints(version: str, spec: dict[str, Any], *, check: bool) -> None:
    endpoints = sorted(
        parse_endpoints(version, spec), key=lambda e: (e.resource, e.path, e.http_method)
    )
    detect_collisions(endpoints)

    by_resource: dict[str, list[Endpoint]] = defaultdict(list)
    for endpoint in endpoints:
        by_resource[endpoint.resource].append(endpoint)

    version_dir = GENERATED_DIR / version
    if not check:
        version_dir.mkdir(parents=True, exist_ok=True)
    generated: dict[Path, str] = {}
    generated[version_dir / "resources.py"] = render_resources(version, by_resource)

    # Format all files in one batch
    ordered = sorted(generated)
    contents = format_python([generated[p] for p in ordered])
    for path, content in zip(ordered, contents):
        if check:
            assert_same(path, content)
        else:
            path.write_text(content)

    _print_summary(version, endpoints, by_resource, ordered)


def detect_collisions(endpoints: list[Endpoint]) -> None:
    by_func: dict[tuple[str, str], list[Endpoint]] = defaultdict(list)
    by_public: dict[tuple[str, str], list[Endpoint]] = defaultdict(list)
    for ep in endpoints:
        by_func[(ep.resource, ep.function_name)].append(ep)
        by_public[(ep.resource, ep.public_method_name)].append(ep)

    _raise_collisions(by_func, "function_name")
    _raise_collisions(by_public, "public method")


def _raise_collisions(grouped: dict[tuple[str, str], list[Endpoint]], field_name: str) -> None:
    for (resource, name), endpoints in grouped.items():
        if len(endpoints) <= 1:
            continue
        paths = ", ".join(f"{e.http_method.upper()} {e.path}" for e in endpoints)
        raise SystemExit(
            f"Collision: resource {resource!r} has duplicate {field_name} {name!r} "
            f"for endpoints: {paths}"
        )


def _print_summary(
    version: str,
    endpoints: list[Endpoint],
    by_resource: dict[str, list[Endpoint]],
    files: list[Path],
) -> None:
    n_overrides = sum(1 for ep in endpoints if ep.response_model is None or ep.body_kind != "none")
    print(f"  {version}: {len(by_resource)} resources, {len(endpoints)} endpoints", file=sys.stderr)
    if n_overrides:
        print(f"  {version}: {n_overrides} endpoints use overrides", file=sys.stderr)
    print(f"  generated: {', '.join(p.name for p in files)}", file=sys.stderr)


def assert_same(path: Path, generated: str) -> None:
    current = path.read_text() if path.exists() else ""
    if current == generated:
        return
    diff = "".join(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            generated.splitlines(keepends=True),
            fromfile=str(path),
            tofile=f"{path} (generated)",
        )
    )
    sys.stderr.write(diff)
    raise SystemExit(1)

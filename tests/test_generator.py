import json
import sys
from importlib.util import module_from_spec, spec_from_file_location
from types import ModuleType
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sdk_generator.generate import detect_collisions, generate_model_file
from sdk_generator.models import Endpoint, HTTPMethod
from sdk_generator.naming import singular, to_snake
from sdk_generator.openapi import (
    infer_endpoint,
    infer_function_name,
    infer_public_method_name,
    infer_resource,
    load_openapi,
    parse_endpoints,
    parse_params,
    schema_ref_name,
)
from sdk_generator.render import format_python


def import_generated_models(tmp_path, schemas) -> ModuleType:
    target = tmp_path / "models.py"
    generate_model_file(
        "v2",
        {
            "openapi": "3.1.0",
            "info": {"title": "test", "version": "1"},
            "paths": {},
            "components": {"schemas": schemas},
        },
        target,
        reuse_model=False,
        collapse_reuse_models=False,
    )
    module_name = f"generated_models_{uuid4().hex}"
    spec = spec_from_file_location(module_name, target)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# ── naming ──


@pytest.mark.parametrize(
    "input_val,expected",
    [
        ("regions", "regions"),
        ("calculations", "calculations"),
        ("ExternalV2Regions", "external_v2_regions"),
        ("GetRegion", "get_region"),
        ("black-oil-tables", "black_oil_tables"),
    ],
)
def test_to_snake(input_val, expected):
    assert to_snake(input_val) == expected


def test_singular():
    assert singular("regions") == "region"
    assert singular("wells") == "well"
    assert singular("samples") == "sample"
    assert singular("properties") == "property"


# ── param parsing ──


def test_parse_params_path_and_query():
    raw = [
        {"name": "region_id", "in": "path", "required": True, "schema": {"type": "integer"}},
        {"name": "cursor", "in": "query", "schema": {"type": "string"}},
        {"name": "limit", "in": "query", "schema": {"type": "integer"}},
    ]
    params = parse_params(raw)
    assert len(params) == 3
    assert params[0].python_name == "region_id"
    assert params[0].location == "path"
    assert params[0].python_type == "int"
    assert params[0].required is True
    assert params[1].python_name == "cursor"
    assert params[1].required is False
    assert params[2].python_name == "limit"
    assert params[2].python_type == "int"


def test_parse_params_skips_ref():
    raw = [{"$ref": "#/components/parameters/Foo"}]
    assert parse_params(raw) == []


# ── schema ref ──


@pytest.mark.parametrize(
    ("schema", "expected"),
    [
        ({"$ref": "#/components/schemas/GetRegionModel"}, "GetRegionModel"),
        (
            {"type": "array", "items": {"$ref": "#/components/schemas/CreateSampleListModel"}},
            "CreateSampleListModel",
        ),
        (None, None),
        ({}, None),
    ],
    ids=["ref", "array-items", "none", "empty"],
)
def test_schema_ref_name(schema, expected):
    assert schema_ref_name(schema) == expected


def test_load_openapi_renames_schemas_and_refs_by_their_titles(tmp_path):
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "test", "version": "1"},
        "paths": {
            "/calculations/flash": {
                "post": {
                    "operationId": "run_flash",
                    "tags": ["calculations"],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": (
                                        "#/components/schemas/ExternalFlashCalculationInputModel"
                                    )
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": (
                                            "#/components/schemas/"
                                            "ExternalFlashCalculationResponseModel"
                                        )
                                    }
                                }
                            }
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "ExternalFlashCalculationInputModel": {
                    "type": "object",
                    "title": "Flash Calculation Input Model",
                    "properties": {
                        "sample": {"$ref": "#/components/schemas/ExternalCreateSampleModel"}
                    },
                },
                "ExternalFlashCalculationResponseModel": {
                    "type": "object",
                    "title": "Flash Calculation Response Model",
                },
                "CreateSampleModel": {
                    "type": "object",
                    "title": "CreateSampleModel",
                    "properties": {"name": {"type": "string"}},
                },
                "ExternalCreateSampleModel": {
                    "type": "object",
                    "title": "CreateSampleModel",
                    "properties": {"name": {"type": "string"}},
                },
            }
        },
    }
    openapi_path = tmp_path / "openapi.json"
    openapi_path.write_text(json.dumps(spec))

    normalized = load_openapi("v2", openapi_path, "http://localhost:4000/external")
    schemas = normalized["components"]["schemas"]

    assert "ExternalFlashCalculationInputModel" not in schemas
    assert "FlashCalculationInputModel" in schemas
    assert "ExternalCreateSampleModel" not in schemas
    assert "CreateSampleModel" in schemas
    assert (
        normalized["paths"]["/calculations/flash"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        == "#/components/schemas/FlashCalculationInputModel"
    )
    assert (
        schemas["FlashCalculationInputModel"]["properties"]["sample"]["$ref"]
        == "#/components/schemas/CreateSampleModel"
    )


# ── model generation ──


def test_generated_named_enum_is_a_string_literal(tmp_path):
    module = import_generated_models(
        tmp_path,
        {
            "GorUnit": {"type": "string", "enum": ["Sm3/Sm3", "Sm3/m3"], "title": "GorUnit"},
            "SampleModel": {
                "type": "object",
                "properties": {"initial_gor_unit": {"$ref": "#/components/schemas/GorUnit"}},
            },
        },
    )

    unit = module.SampleModel(initial_gor_unit="Sm3/Sm3").initial_gor_unit
    assert type(unit) is str
    assert unit == "Sm3/Sm3"
    with pytest.raises(ValidationError):
        module.SampleModel(initial_gor_unit="bbl/bbl")


def test_generated_constrained_scalar_alias_validates_model_fields(tmp_path):
    module = import_generated_models(
        tmp_path,
        {
            "MassAmount": {"type": "number", "minimum": 0.0, "title": "MassAmount"},
            "CompositionModel": {
                "type": "object",
                "properties": {"mass_amount": {"$ref": "#/components/schemas/MassAmount"}},
            },
        },
    )

    assert module.CompositionModel(mass_amount=1.0).mass_amount == 1.0
    with pytest.raises(ValidationError):
        module.CompositionModel(mass_amount=-1.0)


def test_generated_array_root_model_accepts_root_and_exposes_root(tmp_path):
    module = import_generated_models(
        tmp_path,
        {
            "CreateSampleModel": {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
            },
            "CreateSampleListModel": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/CreateSampleModel"},
                "title": "CreateSampleListModel",
            },
        },
    )

    sample = module.CreateSampleModel(name="S1")
    data = module.CreateSampleListModel(root=[sample])
    assert data.root == [sample]
    assert data.model_dump() == [{"name": "S1"}]


# ── inference ──


@pytest.mark.parametrize(
    ("path", "operation", "expected"),
    [
        ("/any/path", {"tags": ["regions"]}, "regions"),
        ("/black-oil-tables/{id}", {}, "black_oil_tables"),
    ],
    ids=["tag", "path"],
)
def test_infer_resource(path, operation, expected):
    assert infer_resource(path, operation) == expected


@pytest.mark.parametrize(
    ("method", "path", "resource", "operation", "expected"),
    [
        ("get", "/regions", "regions", {"operationId": "list_regions"}, "list_regions"),
        ("get", "/regions", "regions", {}, "list_regions"),
        ("get", "/regions/{id}", "regions", {}, "get_region"),
        ("post", "/regions", "regions", {}, "create_region"),
        ("put", "/regions/{id}", "regions", {}, "update_region"),
        ("post", "/samples/bulk", "samples", {}, "create_samples_bulk"),
        ("put", "/wells/bulk", "wells", {}, "update_wells_bulk"),
    ],
    ids=["operation-id", "list", "get", "create", "update", "post-bulk", "put-bulk"],
)
def test_infer_function_name(method, path, resource, operation, expected):
    assert infer_function_name(method, path, resource, operation) == expected


@pytest.mark.parametrize(
    ("function_name", "resource", "method", "path", "body_kind", "expected"),
    [
        ("list_regions", "regions", "get", "/regions", "none", "list"),
        ("get_region", "regions", "get", "/regions/{id}", "none", "get"),
        ("create_region", "regions", "post", "/regions", "model", "create"),
        ("update_region", "regions", "put", "/regions/{id}", "model", "update"),
        ("create_samples", "samples", "post", "/samples/bulk", "root_list", "create_bulk"),
        ("update_wells", "wells", "put", "/wells/bulk", "root_list", "update_bulk"),
        ("list_wells_info", "wells", "get", "/regions/{region_id}/wells", "none", "list"),
        ("run_flash", "calculations", "post", "/calculations/flash", "model", "run_flash"),
    ],
    ids=["list", "get", "create", "update", "create-bulk", "update-bulk", "nested-list", "other"],
)
def test_infer_public_method_name(function_name, resource, method, path, body_kind, expected):
    assert infer_public_method_name(function_name, resource, method, path, body_kind) == expected


def test_infer_endpoint_post_with_body():
    op = {
        "operationId": "create_region",
        "requestBody": {
            "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/CreateRegionModel"}}
            }
        },
        "responses": {
            "201": {
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/GetRegionModel"}}
                }
            }
        },
    }
    ep = infer_endpoint("v2", "post", "/regions", op, [])
    assert ep.request_model == "CreateRegionModel"
    assert ep.response_model == "GetRegionModel"
    assert ep.body_kind == "model"


def test_infer_endpoint_post_list_model():
    op = {
        "operationId": "create_samples",
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/CreateSampleListModel"}
                }
            }
        },
        "responses": {
            "201": {
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/GetSampleListModel"}
                    }
                }
            }
        },
    }
    ep = infer_endpoint("v2", "post", "/samples/bulk", op, [])
    assert ep.function_name == "create_samples"
    assert ep.public_method_name == "create_bulk"
    assert ep.body_kind == "root_list"


# ── collision detection ──


def _endpoint(
    function_name: str, public_method_name: str, method: HTTPMethod, path: str
) -> Endpoint:
    return Endpoint(
        version="v2",
        resource="r",
        function_name=function_name,
        public_method_name=public_method_name,
        http_method=method,
        path=path,
    )


@pytest.mark.parametrize(
    ("endpoints", "error"),
    [
        ([_endpoint("list_r", "list", "get", "/r")], None),
        (
            [_endpoint("foo", "list", "get", "/r"), _endpoint("foo", "list2", "post", "/r")],
            "duplicate function_name",
        ),
        (
            [_endpoint("foo", "bar", "get", "/r"), _endpoint("baz", "bar", "post", "/r2")],
            "duplicate public method",
        ),
    ],
    ids=["distinct", "function-name", "public-method"],
)
def test_detect_collisions(endpoints, error):
    if error is None:
        detect_collisions(endpoints)
    else:
        with pytest.raises(SystemExit, match=error):
            detect_collisions(endpoints)


# ── parsing ──


@pytest.mark.parametrize(
    ("operation", "error"),
    [
        ({"operationId": "list_widgets", "responses": {}}, "No recognized response status"),
        ({"$ref": "#/paths/foo"}, "Unsupported \\$ref operation"),
        ({"operationId": "list_widgets", "responses": {"200": {}}}, "No response schema"),
    ],
    ids=["no-response", "ref", "no-response-schema"],
)
def test_parse_endpoints_rejects_an_unusable_operation(operation, error):
    spec = {"paths": {"/widgets": {"get": {"tags": ["widgets"], **operation}}}}

    with pytest.raises(SystemExit, match=f"{error}.* /widgets"):
        parse_endpoints("v2", spec)


def test_parse_endpoints_allows_bytes_override_without_response_schema():
    spec = {
        "paths": {
            "/reports/{report_id}/export": {
                "get": {
                    "operationId": "get_report_export",
                    "tags": ["reports"],
                    "parameters": [
                        {
                            "name": "report_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                        }
                    ],
                    "responses": {"200": {}},
                }
            }
        }
    }

    endpoints = parse_endpoints("v2", spec)

    assert endpoints[0].return_kind == "tuple_bytes_filename"
    assert endpoints[0].response_model is None


def test_format_python_applies_ruff_fixes():
    formatted = format_python("import sys\nimport os\n\nprint(sys.version)\n")

    assert isinstance(formatted, str)
    assert "import os" not in formatted
    assert formatted.startswith("import sys\n")


def test_parse_endpoints_infers_pagination_item_field_and_model():
    spec = {
        "components": {
            "schemas": {
                "PaginatedRegionsModel": {
                    "properties": {
                        "pagination": {"$ref": "#/components/schemas/PaginationMeta"},
                        "regions": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/GetRegionModel"},
                        },
                    }
                }
            }
        },
        "paths": {
            "/regions": {
                "get": {
                    "operationId": "list_regions",
                    "tags": ["regions"],
                    "parameters": [
                        {"name": "cursor", "in": "query", "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                    ],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/PaginatedRegionsModel"}
                                }
                            }
                        }
                    },
                }
            }
        },
    }

    endpoints = parse_endpoints("v2", spec)

    assert endpoints[0].pagination_items_field == "regions"
    assert endpoints[0].pagination_item_model == "GetRegionModel"


def test_parse_endpoints_excludes_authentication_resource():
    spec = {
        "paths": {
            "/auth/token": {
                "post": {
                    "operationId": "get_token",
                    "tags": ["authentication"],
                    "responses": {"200": {"content": {"application/json": {}}}},
                }
            }
        }
    }

    assert parse_endpoints("v2", spec) == []

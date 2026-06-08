import pytest
from sdk_generator.generate import detect_collisions
from sdk_generator.models import (
    Endpoint,
    EndpointParam,
)
from sdk_generator.naming import singular, to_snake
from sdk_generator.openapi import (
    _validate_operation,
    apply_override,
    infer_endpoint,
    infer_function_name,
    infer_public_method_name,
    infer_resource,
    parse_endpoints,
    parse_params,
    schema_ref_name,
)
from sdk_generator.render import (
    format_python,
    render_endpoint,
    render_module,
    render_resources,
)

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


def test_schema_ref_name_from_ref():
    assert schema_ref_name({"$ref": "#/components/schemas/GetRegionModel"}) == "GetRegionModel"


def test_schema_ref_name_array_items():
    schema = {"type": "array", "items": {"$ref": "#/components/schemas/CreateSampleListModel"}}
    assert schema_ref_name(schema) == "CreateSampleListModel"


def test_schema_ref_name_none():
    assert schema_ref_name(None) is None
    assert schema_ref_name({}) is None


# ── resource inference ──


def test_infer_resource_from_tags():
    assert infer_resource("/any/path", {"tags": ["regions"]}) == "regions"


def test_infer_resource_from_path():
    assert infer_resource("/black-oil-tables/{id}", {}) == "black_oil_tables"


# ── function name inference ──


def test_infer_function_name_from_operation_id():
    op = {"operationId": "list_regions"}
    assert infer_function_name("get", "/regions", "regions", op) == "list_regions"


def test_infer_function_name_fallback_list():
    assert infer_function_name("get", "/regions", "regions", {}) == "list_regions"


def test_infer_function_name_fallback_get():
    assert infer_function_name("get", "/regions/{id}", "regions", {}) == "get_region"


def test_infer_function_name_fallback_create():
    assert infer_function_name("post", "/regions", "regions", {}) == "create_region"


def test_infer_function_name_fallback_update():
    assert infer_function_name("put", "/regions/{id}", "regions", {}) == "update_region"


def test_infer_function_name_fallback_post_bulk():
    assert infer_function_name("post", "/samples/bulk", "samples", {}) == "create_samples_bulk"


def test_infer_function_name_fallback_put_bulk():
    assert infer_function_name("put", "/wells/bulk", "wells", {}) == "update_wells_bulk"


# ── public method name ──


def test_infer_public_method_name_standard():
    assert infer_public_method_name("list_regions", "regions", "get", "/regions", "none") == "list"
    assert (
        infer_public_method_name("get_region", "regions", "get", "/regions/{id}", "none")
        == "get"
    )
    assert (
        infer_public_method_name("create_region", "regions", "post", "/regions", "model")
        == "create"
    )
    assert (
        infer_public_method_name("update_region", "regions", "put", "/regions/{id}", "model")
        == "update"
    )
    assert (
        infer_public_method_name("create_samples", "samples", "post", "/samples/bulk", "root_list")
        == "create_bulk"
    )
    assert (
        infer_public_method_name("update_wells", "wells", "put", "/wells/bulk", "root_list")
        == "update_bulk"
    )


def test_infer_public_method_name_nested_list():
    assert (
        infer_public_method_name(
            "list_wells_info", "wells", "get", "/regions/{region_id}/wells", "none"
        )
        == "list"
    )


def test_infer_public_method_name_non_standard():
    assert (
        infer_public_method_name(
            "run_flash", "calculations", "post", "/calculations/flash", "model"
        )
        == "run_flash"
    )


# ── endpoint inference ──


def test_infer_endpoint_simple_get():
    ep = infer_endpoint(
        "v2", "get", "/regions", {"operationId": "list_regions", "responses": {"200": {}}}, []
    )
    assert ep.function_name == "list_regions"
    assert ep.public_method_name == "list"
    assert ep.resource == "regions"
    assert ep.body_kind == "none"


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


# ── overrides ──


def test_override_reports_export():
    ep = Endpoint(
        version="v1",
        resource="reports",
        function_name="get_report_export",
        public_method_name="get_report_export",
        http_method="get",
        path="/reports/{report_id}/export",
        path_params=[
            EndpointParam(
                name="report_id", location="path", python_name="report_id", python_type="int"
            ),
        ],
    )
    result = apply_override(ep)
    assert result.function_name == "export_report"
    assert result.public_method_name == "export"
    assert result.return_kind == "tuple_bytes_filename"


def test_override_wells_create_excludes_samples():
    ep = Endpoint(
        version="v1",
        resource="wells",
        function_name="create_well",
        public_method_name="create",
        http_method="post",
        path="/wells",
        request_model="CreateWellModel",
        body_kind="model",
    )
    result = apply_override(ep)
    assert 'exclude={"samples"}' in (result.model_dump_expr or "")


# ── collision detection ──


def test_detect_collisions_ok():
    endpoints = [
        Endpoint(
            version="v1",
            resource="r",
            function_name="list_r",
            public_method_name="list",
            http_method="get",
            path="/r",
        ),
    ]
    detect_collisions(endpoints)


def test_detect_collisions_function_name():
    endpoints = [
        Endpoint(
            version="v1",
            resource="r",
            function_name="foo",
            public_method_name="list",
            http_method="get",
            path="/r",
        ),
        Endpoint(
            version="v1",
            resource="r",
            function_name="foo",
            public_method_name="list2",
            http_method="post",
            path="/r",
        ),
    ]
    with pytest.raises(SystemExit, match="duplicate function_name"):
        detect_collisions(endpoints)


def test_detect_collisions_public_method():
    endpoints = [
        Endpoint(
            version="v1",
            resource="r",
            function_name="foo",
            public_method_name="bar",
            http_method="get",
            path="/r",
        ),
        Endpoint(
            version="v1",
            resource="r",
            function_name="baz",
            public_method_name="bar",
            http_method="post",
            path="/r2",
        ),
    ]
    with pytest.raises(SystemExit, match="duplicate public method"):
        detect_collisions(endpoints)


# ── validation ──


def test_validate_operation_ok():
    _validate_operation("get", "/regions", {"responses": {"200": {}}})


def test_validate_operation_no_response():
    with pytest.raises(SystemExit):
        _validate_operation("get", "/regions", {"responses": {}})


def test_validate_operation_ref():
    with pytest.raises(SystemExit):
        _validate_operation("get", "/regions", {"$ref": "#/paths/foo"})


def test_parse_endpoints_rejects_missing_response_schema():
    spec = {
        "paths": {
            "/widgets": {
                "get": {
                    "operationId": "list_widgets",
                    "tags": ["widgets"],
                    "responses": {"200": {}},
                }
            }
        }
    }

    with pytest.raises(SystemExit, match="No response schema for GET /widgets"):
        parse_endpoints("v1", spec)


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

    endpoints = parse_endpoints("v1", spec)

    assert endpoints[0].return_kind == "tuple_bytes_filename"
    assert endpoints[0].response_model is None


# ── rendering ──


def test_render_endpoint_strips_extra_newlines():
    ep = Endpoint(
        version="v1",
        resource="regions",
        function_name="get_region",
        public_method_name="get",
        http_method="get",
        path="/regions/{region_id}",
        path_params=[
            EndpointParam(
                name="region_id", location="path", python_name="region_id", python_type="int"
            ),
        ],
        response_model="GetRegionModel",
    )
    formatted = format_python(render_endpoint(ep))
    assert "def get_region" in formatted
    assert "model_validate" in formatted
    assert formatted.count("def get_region") == 1


def test_format_python_applies_ruff_fixes():
    formatted = format_python("import sys\nimport os\n\nprint(sys.version)\n")

    assert isinstance(formatted, str)
    assert "import os" not in formatted
    assert formatted.startswith("import sys\n")


def test_render_bytes_endpoint():
    ep = Endpoint(
        version="v1",
        resource="reports",
        function_name="export_report",
        public_method_name="export",
        http_method="get",
        path="/reports/{report_id}/export",
        path_params=[
            EndpointParam(
                name="report_id", location="path", python_name="report_id", python_type="int"
            ),
        ],
        return_kind="tuple_bytes_filename",
        filename_expr='f"report_{report_id}_export.zip"',
    )
    rendered = render_endpoint(ep)
    assert "get_bytes" in rendered
    assert "tuple[bytes, str]" in rendered


def test_render_module_imports():
    ep = Endpoint(
        version="v2",
        resource="regions",
        function_name="list_regions",
        public_method_name="list",
        http_method="get",
        path="/regions",
        query_params=[
            EndpointParam(
                name="cursor",
                location="query",
                python_name="cursor",
                python_type="str",
                required=False,
            ),
            EndpointParam(
                name="limit",
                location="query",
                python_name="limit",
                python_type="int",
                required=False,
            ),
        ],
        response_model="PaginatedRegionsModel",
    )
    rendered = render_module("v2", "regions", [ep])
    assert "from ...http import HTTPTransport" in rendered
    assert "from ...shared.models import PaginationParams" in rendered
    assert "from ...v2.models import" in rendered
    assert "PaginatedRegionsModel" in rendered


def test_render_resources_output():
    ep = Endpoint(
        version="v1",
        resource="regions",
        function_name="list_regions",
        public_method_name="list",
        http_method="get",
        path="/regions",
        response_model="RegionsListModel",
    )
    rendered = render_resources("v1", {"regions": [ep]})
    assert "class Regions:" in rendered
    assert "def list(self" in rendered


# ── full parse ──


def test_parse_endpoints_basic():
    spec = {
        "paths": {
            "/regions": {
                "get": {
                    "operationId": "list_regions",
                    "tags": ["regions"],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/RegionsListModel"}
                                }
                            }
                        }
                    },
                }
            }
        }
    }
    endpoints = parse_endpoints("v1", spec)
    assert len(endpoints) == 1
    assert endpoints[0].function_name == "list_regions"


def test_parse_endpoints_applies_overrides():
    spec = {
        "paths": {
            "/reports/{report_id}/export": {
                "get": {
                    "operationId": "export_report",
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
    endpoints = parse_endpoints("v1", spec)
    assert endpoints[0].return_kind == "tuple_bytes_filename"
    assert endpoints[0].function_name == "export_report"


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

    assert parse_endpoints("v1", spec) == []

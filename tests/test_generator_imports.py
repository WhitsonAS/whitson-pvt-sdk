from sdk_generator.openapi import parse_endpoints
from sdk_generator.render import render_endpoint, render_resources


def _json_body(model):
    return {"content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{model}"}}}}


def test_generator_supports_import_session_methods_and_bodies():
    spec = {
        "paths": {
            "/import-sessions": {
                "post": {
                    "tags": ["Import Sessions"],
                    "requestBody": {
                        "content": {
                            "multipart/form-data": {
                                "schema": {
                                    "$ref": "#/components/schemas/CreateImportSessionFormModel"
                                }
                            }
                        }
                    },
                    "responses": {"201": _json_body("ImportSessionModel")},
                }
            },
            "/import-sessions/{import_session_id}": {
                "delete": {
                    "tags": ["Import Sessions"],
                    "responses": {
                        "204": {"description": "Deleted"},
                        "default": _json_body("ErrorModel"),
                    },
                }
            },
            "/import-sessions/{import_session_id}/commit": {
                "post": {
                    "tags": ["Import Sessions"],
                    "requestBody": _json_body("ImportCommitRequestModel"),
                    "responses": {"200": _json_body("ImportCommitResultModel")},
                }
            },
            "/import-sessions/{import_session_id}/records/{import_record_id}/resolution": {
                "patch": {
                    "tags": ["Import Sessions"],
                    "requestBody": _json_body("ImportRecordResolutionModel"),
                    "responses": {"200": _json_body("ImportRecordModel")},
                }
            },
        }
    }
    endpoints = parse_endpoints("v2", spec)
    by_method = {endpoint.public_method_name: endpoint for endpoint in endpoints}
    assert set(by_method) == {"create", "delete", "commit", "update_resolution"}
    assert by_method["create"].request_model == "ImportSessionCreateOptionsModel"
    assert by_method["commit"].request_model == "ImportCommitRequestModel"
    assert by_method["update_resolution"].http_method == "patch"
    assert by_method["delete"].return_kind == "none"
    assert by_method["delete"].response_model is None

    rendered = render_resources("v2", {"import_sessions": endpoints})
    assert "options: ImportSessionCreateOptionsModel | None = None" in rendered
    assert "options = ImportSessionCreateOptionsModel()" in rendered
    assert "self._transport.patch(" in rendered
    assert "self._transport.delete(" in rendered
    assert "None.model_validate" not in rendered
    assert "None.model_validate" not in render_endpoint(by_method["delete"])
    compile(rendered, "resources.py", "exec")


def test_generator_preserves_filters_and_download_query_params():
    params = [
        {"name": "cursor", "in": "query", "schema": {"type": "string"}},
        {"name": "limit", "in": "query", "schema": {"type": "integer"}},
        {"name": "name", "in": "query", "schema": {"type": "string"}},
    ]
    spec = {
        "paths": {
            "/regions": {
                "get": {
                    "tags": ["Regions"],
                    "parameters": params,
                    "responses": {"200": _json_body("PaginatedRegionsModel")},
                }
            },
            "/reports/{report_id}/export": {
                "get": {
                    "tags": ["Reports"],
                    "parameters": [
                        {"name": "format", "in": "query", "schema": {"type": "string"}},
                        {
                            "name": "include_structured_experiments",
                            "in": "query",
                            "schema": {"type": "boolean"},
                        },
                    ],
                    "responses": {"200": {}},
                }
            },
        }
    }
    regions, export = parse_endpoints("v2", spec)
    for rendered in (render_endpoint(regions), render_resources("v2", {"regions": [regions]})):
        assert "PaginationParams(cursor=cursor, limit=limit)" in rendered
        assert '"name": name' in rendered
        assert "if value is not None" in rendered
    for rendered in (render_endpoint(export), render_resources("v2", {"reports": [export]})):
        assert "include_structured_experiments: bool | None = None" in rendered
        assert "params=" in rendered
        assert '"format": format' in rendered
        assert "if value is not None" in rendered

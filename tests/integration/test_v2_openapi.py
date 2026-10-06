import inspect

from sdk_generator.config import EXCLUDED_RESOURCES
from sdk_generator.openapi import load_openapi, parse_endpoints

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.shared.models import ClientCredentials


def test_live_openapi_operations_are_exposed_on_client(integration_base_url):
    """Read-only check; requires the API URL but no credentials or test data."""
    spec = load_openapi("v2", None, f"{integration_base_url.rstrip('/')}/external")
    endpoints = parse_endpoints("v2", spec)
    documented = {
        (method, path)
        for path, item in spec["paths"].items()
        for method, operation in item.items()
        if method in {"get", "post", "put", "patch", "delete", "head", "options"}
        and not any(tag.lower() in EXCLUDED_RESOURCES for tag in operation.get("tags", []))
    }
    assert {(endpoint.http_method, endpoint.path) for endpoint in endpoints} == documented

    client = WhitsonPVTClient(
        credentials=ClientCredentials(client_id="unused", client_secret="unused"),
        base_url=integration_base_url,
    )
    try:
        for endpoint in endpoints:
            resource = getattr(client, endpoint.resource)
            method = getattr(resource, endpoint.public_method_name)
            signature = inspect.signature(method)
            expected = {param.python_name for param in endpoint.path_params + endpoint.query_params}
            if endpoint.body_kind == "multipart":
                expected |= {"archive_data", "options"}
            elif endpoint.request_model:
                expected.add("data")
            assert expected == set(signature.parameters), endpoint.path
    finally:
        client._transport.close()

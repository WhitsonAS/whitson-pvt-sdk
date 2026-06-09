from pathlib import Path

from sdk_generator.models import EndpointOverride

ROOT = Path(__file__).resolve().parents[2]
SDK_DIR = ROOT / "whitson_pvt_sdk"
GENERATED_DIR = SDK_DIR / "_generated"

HTTP_METHODS = {"get", "post", "put"}
SUPPORTED_VERSIONS = ("v1", "v2")
EXCLUDED_RESOURCES = {"authentication"}

OVERRIDES: dict[tuple[str, str, str], EndpointOverride] = {
    ("*", "get", "/reports/{report_id}/export"): EndpointOverride(
        resource="reports",
        function_name="export_report",
        public_method_name="export",
        response_model=None,
        return_kind="tuple_bytes_filename",
        filename_expr='f"report_{report_id}_export.zip"',
    ),
    ("*", "post", "/reports/import/preflight"): EndpointOverride(
        resource="reports",
        function_name="preflight_import",
        public_method_name="preflight_import",
        request_model="ImportArchiveOptions",
        body_kind="multipart",
    ),
    ("*", "post", "/reports/import"): EndpointOverride(
        resource="reports",
        function_name="import_report",
        public_method_name="import_archive",
        request_model="ImportArchiveOptions",
        body_kind="multipart",
    ),
    ("*", "post", "/wells"): EndpointOverride(
        model_dump_expr='data.model_dump(exclude={"samples"}, exclude_unset=True)',
    ),
}

RESOURCE_CLASS_NAMES = {
    "black_oil_tables": "BlackOilTables",
    "fluid_models": "FluidModels",
}

RESOURCE_ORDER = (
    "regions",
    "wells",
    "samples",
    "projects",
    "fluid_models",
    "black_oil_tables",
    "reports",
    "calculations",
)

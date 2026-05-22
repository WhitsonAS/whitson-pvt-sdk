from __future__ import annotations

from pathlib import Path

from sdk_generator.models import EndpointOverride

ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = ROOT / "whitson_pvt_sdk" / "models"
SDK_DIR = ROOT / "whitson_pvt_sdk"

HTTP_METHODS = {"get", "post", "put"}
SUPPORTED_VERSIONS = ("v1", "v2")

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
        request_model="ExternalImportArchiveOptions",
        body_kind="multipart",
    ),
    ("*", "post", "/reports/import"): EndpointOverride(
        resource="reports",
        function_name="import_report",
        public_method_name="import_archive",
        request_model="ExternalImportArchiveOptions",
        body_kind="multipart",
    ),
    ("*", "post", "/wells"): EndpointOverride(
        model_dump_expr='data.model_dump(exclude={"samples"}, exclude_unset=True)',
    ),
}

EXTRA_RESOURCE_METHODS: dict[str, dict[str, list[str]]] = {
    "v1": {
        "samples": [
            "    def experiment_types(\n"
            "        self, sample_id: int\n"
            "    ) -> list[str]:  # ty: ignore[invalid-type-form]\n"
            "        return samples.get_sample_experiment_types(self._transport, sample_id)\n"
        ]
    },
    "v2": {
        "samples": [
            "    def experiment_types(\n"
            "        self, sample_id: int\n"
            "    ) -> list[str]:  # ty: ignore[invalid-type-form]\n"
            "        return samples.get_sample_experiment_types(self._transport, sample_id)\n"
        ]
    },
}

EXTRA_MODULE_FUNCTIONS: dict[str, dict[str, list[str]]] = {
    "v1": {
        "samples": [
            "def get_sample_experiment_types(\n"
            "    transport: HTTPTransport, sample_id: int\n"
            ") -> list[str]:\n"
            '    body = transport.get(f"/samples/{sample_id}")\n'
            '    experiments = body.get("experiments", [])\n'
            '    return sorted({e.get("type", "Unknown") for e in experiments})\n'
        ]
    },
    "v2": {
        "samples": [
            "def get_sample_experiment_types(\n"
            "    transport: HTTPTransport, sample_id: int\n"
            ") -> list[str]:\n"
            '    body = transport.get(f"/samples/{sample_id}")\n'
            '    experiments = body.get("experiments", [])\n'
            '    return sorted({e.get("type", "Unknown") for e in experiments})\n'
        ]
    },
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

from io import BytesIO

from ..models import (
    ExternalImportArchiveOptions,
    ExternalImportCommitResultModel,
    ExternalImportPreflightResultModel,
)
from ..http import HTTPTransport


def export_report(transport: HTTPTransport, report_id: int) -> tuple[bytes, str]:
    data = transport.get_bytes(f"/reports/{report_id}/export")
    filename = f"report_{report_id}_export.zip"
    return data, filename


def preflight_import(
    transport: HTTPTransport,
    archive_data: bytes,
    options: ExternalImportArchiveOptions | None = None,
) -> ExternalImportPreflightResultModel:
    if options is None:
        options = ExternalImportArchiveOptions()

    body = transport.post_multipart(
        "/reports/import/preflight",
        files={"file": ("archive.zip", BytesIO(archive_data), "application/zip")},
        data=_meta_data(options),
    )
    return ExternalImportPreflightResultModel.model_validate(body)


def import_report(
    transport: HTTPTransport,
    archive_data: bytes,
    options: ExternalImportArchiveOptions | None = None,
) -> ExternalImportCommitResultModel:
    if options is None:
        options = ExternalImportArchiveOptions()

    body = transport.post_multipart(
        "/reports/import",
        files={"file": ("archive.zip", BytesIO(archive_data), "application/zip")},
        data=_meta_data(options),
    )
    return ExternalImportCommitResultModel.model_validate(body)


def _meta_data(options: ExternalImportArchiveOptions) -> dict | None:
    dumped = options.model_dump(exclude_unset=True, exclude_defaults=True)
    if not dumped:
        return None
    return {"meta_data": options.model_dump_json(exclude_unset=True, exclude_defaults=True)}

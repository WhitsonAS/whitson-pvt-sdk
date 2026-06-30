from io import BytesIO
from typing import TypeVar

from pydantic import BaseModel

from ...http import HTTPTransport
from ...shared.models import ImportArchiveOptions

_T = TypeVar("_T", bound=BaseModel)


def _import_report(
    transport: HTTPTransport,
    archive_data: bytes,
    options: ImportArchiveOptions | None,
    result_model: type[_T],
) -> _T:
    if options is None:
        options = ImportArchiveOptions()

    body = transport.post_multipart(
        "/reports/import",
        files={"file": ("archive.zip", BytesIO(archive_data), "application/zip")},
        data=_meta_data(options),
    )
    return result_model.model_validate(body)


def _preflight_import(
    transport: HTTPTransport,
    archive_data: bytes,
    options: ImportArchiveOptions | None,
    result_model: type[_T],
) -> _T:
    if options is None:
        options = ImportArchiveOptions()

    body = transport.post_multipart(
        "/reports/import/preflight",
        files={"file": ("archive.zip", BytesIO(archive_data), "application/zip")},
        data=_meta_data(options),
    )
    return result_model.model_validate(body)


def export_report(transport: HTTPTransport, report_id: int) -> tuple[bytes, str]:
    data = transport.get_bytes(f"/reports/{report_id}/export")
    filename = f"report_{report_id}_export.zip"
    return data, filename


def _meta_data(options: ImportArchiveOptions) -> dict | None:
    dumped = options.model_dump(exclude_unset=True, exclude_defaults=True)
    if not dumped:
        return None
    return {"meta_data": options.model_dump_json(exclude_unset=True, exclude_defaults=True)}

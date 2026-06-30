from ...http import HTTPTransport
from ...shared.models import ImportArchiveOptions
from ...v2.models import (
    ImportCommitResultModel,
    ImportPreflightResultModel,
)
from ..shared.reports import _import_report as _shared_import_report
from ..shared.reports import _preflight_import as _shared_preflight_import
from ..shared.reports import export_report

__all__ = ["export_report", "import_report", "preflight_import"]


def import_report(
    transport: HTTPTransport,
    archive_data: bytes,
    options: ImportArchiveOptions | None = None,
) -> ImportCommitResultModel:
    return _shared_import_report(transport, archive_data, options, ImportCommitResultModel)


def preflight_import(
    transport: HTTPTransport,
    archive_data: bytes,
    options: ImportArchiveOptions | None = None,
) -> ImportPreflightResultModel:
    return _shared_preflight_import(transport, archive_data, options, ImportPreflightResultModel)

"""Export and import reports.

Demonstrates:
- Exporting a report to a local zip file
- Running an import preflight check with options
- Importing an archive with resolution options
"""

import os
from pathlib import Path

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.shared.models import (
    ClientCredentials,
    ImportArchiveOptions,
)


def main() -> None:
    client = WhitsonPVTClient(
        credentials=ClientCredentials(
            client_id=os.environ["WHITSON_CLIENT_ID"],
            client_secret=os.environ["WHITSON_CLIENT_SECRET"],
        ),
        base_url=os.environ.get("WHITSON_BASE_URL", "https://internal.pvt.whitson.com"),
    )

    report_id = int(os.environ.get("WHITSON_REPORT_ID", "1"))

    data, filename = client.reports.export(report_id=report_id)
    Path(filename).write_bytes(data)
    print(f"Exported report {report_id} to {filename} ({len(data)} bytes)")

    archive_data = Path(filename).read_bytes()

    preflight = client.reports.preflight_import(
        archive_data,
        options=ImportArchiveOptions(region_id=1),
    )
    print(f"Preflight: can_commit={preflight.can_commit}")
    print(f"  summary: {preflight.summary}")
    print(f"  suggestions: {len(preflight.suggestions)}")
    print(f"  collisions: {len(preflight.collisions)}")

    result = client.reports.import_archive(
        archive_data,
        options=ImportArchiveOptions(
            region_id=1,
            acknowledge_suggestions=True,
        ),
    )
    print(f"Import result: created={result.created}, reused={result.reused}")


if __name__ == "__main__":
    main()

# Updating to the current external API v2

This update targets the current external API **v2**. The SDK package version and
API version are independent: continue using `version="v2"` (the default).
The release version has not yet been bumped.

## Calculation surface-process inputs

Replace these imports and constructors in calculation requests and GOR helpers:

| Previous name | Current calculation-input name |
| --- | --- |
| `SurfaceProcessModel` | `SurfaceProcessInputModel` |
| `SurfaceProcessStageModel` | `SurfaceProcessStageInputModel` |

```python
from whitson_pvt_sdk.v2.models import SurfaceProcessInputModel, SurfaceProcessStageInputModel

surface_process = SurfaceProcessInputModel(
    pressure_unit="bara",
    temperature_unit="C",
    stages=[SurfaceProcessStageInputModel(pressure=1.01325, temperature=15.0)],
)
```

The old names now describe stored surface-process **responses**, with database
IDs and stage indexes. Do not invent IDs to reuse those models as calculation inputs.

## Archive import response type

`client.reports.import_archive(...)` now returns `ReportArchiveCommitResultModel`.
Its `created`, `reused`, `skipped`, and `id_map` fields are unchanged.
Update explicit imports, annotations, and `isinstance` checks.

`ImportCommitResultModel` now describes staged session commits instead:
`import_session_id`, `status`, and per-record `records`.

## Staged import workflow

The API deprecates legacy report import/preflight in favor of:

- `client.import_sessions.create(archive_data, options)` — multipart ZIP upload;
  options use `ImportSessionCreateOptionsModel`, not `ImportArchiveOptions`.
- `get(session_id)` and `list_records(session_id)` — inspect the staged import.
- `update_resolution(session_id, record_id, ImportRecordResolutionModel(...))` —
  resolve records after reviewing proposed changes, warnings, and dependencies.
- `commit(session_id, ImportCommitRequestModel(selected_record_ids=[...]))` —
  commit only the selected records. An empty list selects none; omitting the
  field selects all eligible records. Prefer explicit selections.
- `delete(session_id)` — remove the staging session; this does **not** undo
  previously committed native entities.

Single-record OSDU requests are available through `client.import_records`:
`import_osdu_sample`, `import_osdu_sample_analysis`, `import_osdu_report`, and
`import_osdu_file`. They accept `SingleRecordImportRequestModel`; auto-commit is
opt-in. HTTP 409 conflicts raise `APIError`; structured details remain available
in `response_body` (including the existing session ID for duplicate archives).

## Filters and OSDU export

All five paginated resources support `name=` on `list`, `iterate`, and `list_all`.
The API applies a case-insensitive exact match, ignoring surrounding whitespace.

```python
regions = client.regions.list_all(name="North field")
archive, filename = client.reports.export(
    report_id=123,
    format="osdu",
    include_whitson_native_payload=False,
    include_structured_experiments=True,
)
```

Omit export options to keep the native archive default.

## Deployment compatibility

Calculation output units and flash/saturation phase properties have additional
required fields (some nullable). Upgrade the API deployment before using this SDK
against it; responses from older deployments may fail Pydantic validation.
New sample fields include SSF recombination, MultiContact experiments, expanded
VISCO stages, and swell-test viscosity.

PATCH and DELETE follow the existing conservative write retry policy: no automatic
retry for transport/server failures by default, but HTTP 429 may be retried.

## Verification before release

Run `just test`, `just lint`, `just ty`, `just generate-check v2`, and `just build`.
For live schema/wiring verification without credentials:

```bash
WHITSON_INTEGRATION_BASE_URL=http://localhost:4000 \
  uv run pytest tests/integration/test_v2_openapi.py -v -m integration -o addopts=''
```

For authenticated verification, configure the integration credentials and IDs
listed in the README and run `just integration` against a disposable environment.
The native round-trip test exports the configured report, stages it in a unique
region, commits real entities, reads them back through the SDK, and compares a
re-export including metadata and file hashes. Staging sessions are deleted; native
entities remain for inspection because the external API has no delete endpoints
for them. The separate staged-review test also covers explicit empty selections
and skip resolutions. Live calculation tests must assert successful result rows;
merely receiving a nonempty result list does not demonstrate calculation success.

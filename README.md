# whitson PVT SDK

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](https://github.com/WhitsonAS/whitson-pvt-sdk/blob/main/LICENSE)

HTTP client for the whitson PVT external API. Python 3.10+.

## Install

```bash
# uv (recommended)
uv add whitson-pvt-sdk

# pip
pip install whitson-pvt-sdk
```

## Quick start

Authenticate with an API token. Set `PVT_TOKEN` in the environment, or pass
`token=` explicitly:

```bash
export PVT_TOKEN=whitson_pvt_...
```

```python
from whitson_pvt_sdk import WhitsonPVTClient

with WhitsonPVTClient(base_url="https://internal.pvt.whitson.com") as client:
    # or: WhitsonPVTClient(token="whitson_pvt_...", base_url="https://internal.pvt.whitson.com")
    regions = client.regions.list()
    well = client.wells.get(well_id=123)
    sample = client.samples.get(sample_id=456)
```

Leaving the `with` block closes the client's connections. A client kept for the life
of a process can call `client.close()` instead; closing twice is harmless, and a
request on a closed client raises `RuntimeError`.

Create an API token in whitson PVT under **Developer → Integrations**. Tokens start
with `whitson_pvt_` and are shown once, when they are created.

The token is sent as the bearer token on every request. The `token=` argument takes
precedence over `PVT_TOKEN`. The client raises `ConfigurationError` when neither is set,
or when the one in use is empty.

### Upgrading from 1.x

2.0 authenticates only with API tokens and talks only to external API v2.

- Removed: `ClientCredentials`, the `credentials=` argument, the `/auth/token`
  exchange, `client.get_access_token()`, `whitson_pvt_sdk.auth.TokenManager` and
  `TokenData`. Pass `token=` or set `PVT_TOKEN` instead; the bearer is the token you
  already hold.
- Removed: `version=` and the v1 API (`whitson_pvt_sdk.v1`). API releases that accept
  tokens no longer serve `/external/v1`.
- `WhitsonPVTClient` is now the client class; `whitson_pvt_sdk.v2.WhitsonPVTClientV2`
  is gone. Annotate with `WhitsonPVTClient`.
- The package root exports only `WhitsonPVTClient`. Import `RetryConfig` from
  `whitson_pvt_sdk.shared.models` and `HTTPTransport` from `whitson_pvt_sdk.http`.
- `retry_config=None` is no longer accepted; omit `retry_config` for the defaults.
- `HTTPTransport(credential, base_url, ...)` takes an `ApiToken` from
  `whitson_pvt_sdk.auth`, has no `version` argument and is no longer a context manager.
- `calculations.get_gor_recombination_feed_composition(s)` take the feed composition(s)
  through `source=` instead of `feed_composition(s)=`.
- A missing or empty token raises `ConfigurationError` when the client is created,
  not `AuthError`. `AuthError` now means only that the API answered 401 or 403.
- A request that gets no response (connection error, timeout) raises
  `NoResponseError` instead of `APIError` with `status_code=None`. Every
  `ResponseError` (`AuthError`, `NotFoundError`, `ValidationError`, `RateLimitError`,
  `APIError`) now carries an integer `status_code`.
- `WhitsonPVTClient` has `close()` and works as a context manager; replace any
  `client._transport.close()` with `client.close()` or a `with` block.
- `RetryConfig` is immutable and its `methods` must be upper-case HTTP methods.
- `whitson_pvt_sdk.utils.write_json(data, path=None)` is no longer accepted; omit
  `path` for `output.json`.
- The unused multi-domain copy models (`DomainAuthConfig`, `MultiDomainCopyConfig`
  and related) are removed from `whitson_pvt_sdk.shared.models`.

1.x keeps working with client credentials until the server retires them. Pin
`whitson-pvt-sdk<2` if you cannot switch to a token yet.

### Retries

The SDK retries transient read failures by default. `GET` requests are attempted up
to 3 times for network timeouts/transport errors and HTTP `408`, `429`, `500`,
`502`, `503`, and `504` responses. Mutating requests (`POST`, `PUT`, `PATCH`, `DELETE`, and
multipart uploads) are not retried by default, except on HTTP `429` (rate
limiting).

Retry delays honor `Retry-After`, `retry-after-ms`, and `X-RateLimit-Reset`
headers when present. `X-RateLimit-Limit` and `X-RateLimit-Remaining` are left
available on the raw HTTP response internally, but do not affect retry timing.

If retries are exhausted on HTTP `429`, the SDK raises `RateLimitError` with
`retry_after_seconds` when retry timing headers are present. `max_attempts`
includes the first request; use `RetryConfig(max_attempts=1)` to disable
retries. `RetryConfig.methods` controls non-429 retries only; remove `429` from
`RetryConfig.statuses` to disable all-method rate-limit retries.

Configure retries on the client:

```python
from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.shared.models import RetryConfig

client = WhitsonPVTClient(
    base_url="https://internal.pvt.whitson.com",
    retry_config=RetryConfig(max_attempts=1),  # disables retries
)
```

Configure default request timeouts with `timeout`; downloads and uploads use
`file_timeout`:

```python
client = WhitsonPVTClient(
    base_url="https://internal.pvt.whitson.com",
    timeout=30.0,
    file_timeout=60.0,
)
```

### Errors

Everything the SDK raises derives from `SDKError` in `whitson_pvt_sdk.errors`:

| Error | Raised when | Fields |
| --- | --- | --- |
| `ConfigurationError` | the client is created without a usable token | `message` |
| `NoResponseError` | a request gets no response (connection error, timeout) after retries | `message` |
| `ResponseError` | the API answers with an error status; base of the five below | `status_code`, `response_body`, `request_id` |
| `AuthError` | HTTP 401 or 403 | as `ResponseError` |
| `NotFoundError` | HTTP 404 | as `ResponseError` |
| `ValidationError` | HTTP 400 or 422 | as `ResponseError` |
| `RateLimitError` | HTTP 429 after retries | also `retry_after_seconds` |
| `APIError` | any other error status | as `ResponseError` |
| `CalculationError` | a calculation returns a failed result | `code`, `sample_id`, `input_index`, `error` |

```python
from whitson_pvt_sdk.errors import AuthError, NoResponseError, ResponseError

try:
    region = client.regions.get(region_id=1)
except AuthError:
    ...  # the token was rejected or lacks access
except ResponseError as exc:
    print(exc.status_code, exc.request_id)
except NoResponseError:
    ...  # no response; a write may still have reached the API
```

### Pagination

List endpoints (regions, projects, fluid models, black oil tables, wells) are
cursor-paginated. Use `iterate()` for lazy traversal or `list_all()` for an eager
list:

```python
for region in client.regions.iterate(limit=50):
    print(region.name)

regions = client.regions.list_all(limit=50)
```

Each response still includes a `pagination` field when you need manual cursor
control:

```python
page = client.regions.list()
print(page.pagination.next_cursor)
```

Pass `cursor` and `limit` to control pagination:

```python
page = client.regions.list(limit=50)
page = client.regions.list(cursor=page.pagination.next_cursor)
```

Limit defaults to the API default (usually 20) when omitted. `iterate()` and
`list_all()` are available on all cursor-paginated resources: `regions`,
`wells`, `projects`, `fluid_models`, and `black_oil_tables`.

All five resources also accept `name=` on `list()`, `iterate()`, and `list_all()`.
This is a case-insensitive exact match; the API trims surrounding whitespace.

### Staged imports and OSDU export

`client.import_sessions` exposes archive upload, inspection, per-record resolution,
selected-record commit, and deletion. `client.import_records` exposes the four
single-record OSDU import endpoints.

```python
from pathlib import Path
from whitson_pvt_sdk.v2.models import ImportSessionCreateOptionsModel

session = client.import_sessions.create(
    Path("archive.zip").read_bytes(),
    ImportSessionCreateOptionsModel(region_id=123),
)
records = client.import_sessions.list_records(session.id)
# Review records before calling update_resolution() and commit().
```

Export OSDU archives with `client.reports.export(report_id=123, format="osdu")`.
The native archive format remains the default.

See [Updating to the current external API v2](docs/api-v2-update.md) for changed model names,
commit-selection semantics, and API deployment requirements.

More runnable examples are available in [examples](https://github.com/WhitsonAS/whitson-pvt-sdk/tree/main/examples).

## Development

### Prerequisites

- **[uv](https://docs.astral.sh/uv/)** — Python package & project manager

  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

### Setup

```bash
uv sync                           # installs Python deps + dev tools
uv tool install rust-just         # installs just (command runner) globally
just install-hooks                # installs the commit message hook
```

### Commit Messages

Commit messages use Conventional Commits so release notes can be generated from
Git history. The local `commit-msg` hook validates messages after running
`just install-hooks`.

Use:

```text
type: subject
type(scope): subject
type!: breaking subject
```

Allowed types are `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`,
`ci`, `chore`, and `release`.

Examples:

```text
feat: add pypi publishing workflow
fix(http): normalize localhost base urls
docs: add examples env setup
```

### Tasks

```bash
just lint                        # ruff check
just format                      # ruff format
just ty                          # ty check
just test                        # pytest
just integration                 # opt-in tests against a real API
just build                       # uv build
just generate v2                 # regenerate v2 models and endpoint wrappers
just generate-all                # regenerate every supported version (v2)
just all                         # generate-all + lint/format + build
```

Integration tests are skipped by default. They create an isolated region, well,
sample, and simple experiment for each run so existing staging data is not modified.
The external API does not currently expose delete endpoints for these resources,
so test data is left behind with unique `sdk-it-*` names.
Run them against a real API by setting an API token:

```bash
export WHITSON_INTEGRATION_BASE_URL=https://internal.pvt.whitson.com
export WHITSON_INTEGRATION_TOKEN=whitson_pvt_...

just integration
```

For local testing without a real token, the API supports
`EXTERNAL_API_AUTH_BYPASS=true` with its local/debug safeguards. Restart the API
using the Flask development CLI, bound to `127.0.0.1` with a local database, then
use `local-pvt-sdk-test-token` as the integration token. See "Local SDK Testing" in
`api/pvt_api/external_api/AGENTS.md` in the API repository. The flag belongs to the
API process, not the SDK; do not enable it in deployments.

Optional IDs enable project, fluid-model, calculation, black-oil-table, and report
checks that cannot be backed by created fixtures: `WHITSON_INTEGRATION_PROJECT_ID`,
`WHITSON_INTEGRATION_FLUID_MODEL_ID`, `WHITSON_INTEGRATION_BLACK_OIL_TABLE_ID`,
`WHITSON_INTEGRATION_SAMPLE_ID`, and `WHITSON_INTEGRATION_REPORT_ID`. The sample ID
must have an adjusted composition in the configured fluid model; conversion is
separately tested with a created sample containing a characterized C7+ residue.
Calculation errors fail tests rather than skipping the dependent endpoints.

The report ID enables real native and OSDU archive round trips, legacy preflight/
import, and all four single-record OSDU endpoints. Choose a report with an available
PDF, wells, samples, and RAFS-supported experiments (CCE/CVD/DLE/MSS). The round-trip
tests use only public SDK methods: export → create a unique region → upload → review
→ commit → read back → delete the staging session → re-export. Native and OSDU
high-fidelity tests compare native data and file hashes and check that the source
report is unchanged. Structured OSDU tests compare the data actually represented in
RAFS, not native-only fields.

The round trip leaves its region and imported entities behind (their IDs are logged);
only the staging session can be deleted through the external API. Export failures
are test failures, not skips, and occur before the round-trip region is created.
Integration requests do not retry, so API errors remain visible. To run just this test:

```bash
uv run pytest tests/integration/test_v2_report_roundtrip.py -v -s -m integration -o addopts=''
```

Use `include_whitson_native_payload=True` and `import_mode="whitson_high_fidelity"`
for full native fidelity. RAFS-only archives do not preserve all native metadata,
composition details, primary-experiment flags, or saturation-pressure classifications.
JSON-only File.Generic import intentionally returns an unsupported record without
committing file bytes; use archive import for files. Single-record analysis metadata
needs a reviewed `resolved_payload` with experiment data before committing; set its
`entity_type` discriminator explicitly.

The OpenAPI/wiring test requires only `WHITSON_INTEGRATION_BASE_URL`, not a token.

### Publishing

Publishing uses GitHub Actions and PyPI Trusted Publishing; no PyPI API token is
stored in this repository. Configure the `whitson-pvt-sdk` project on PyPI to
trust this GitHub repository and the `pypi` environment, then publish a GitHub
Release to build and upload the package.

Before creating a release, update `version` in `pyproject.toml` and run:

```bash
just test
just lint
just ty
just publish-check
just release-notes 0.1.1
```

`just release-notes` generates deterministic Markdown from Conventional Commits
since the previous Git tag. Create the GitHub Release with:

```bash
just release 0.1.1
```

The release recipe writes generated notes to a temporary file and passes them to
`gh release create`. Publishing to PyPI starts when the GitHub Release is
published. The GitHub CLI must be authenticated with release permissions; use
`gh auth login` and `gh auth status` to set up and verify access.

### Code generation

Generated code comes from the live API's OpenAPI spec:

This fetches `/external/{version}/docs/openapi.json` from the configured `BASE_URL`, runs `datamodel-code-generator` for Pydantic models, then uses the repo-specific generator in `scripts/sdk_generator/` for endpoint modules and resource facades.

Generated outputs live under:

- `whitson_pvt_sdk/_generated/v2/models.py`
- `whitson_pvt_sdk/_generated/v2/resources.py`
- `whitson_pvt_sdk/v2/models/__init__.py` re-exports generated models

`whitson_pvt_sdk/v2/resources.py` re-exports the public resource classes and adds
hand-written conveniences. Resource classes call `HTTPTransport` directly and expose
SDK-shaped method names such as `list`, `get`, `create`, `update`, `create_bulk`, and
`update_bulk`.

Authentication endpoints are intentionally excluded from generated resources;
auth is infrastructure owned by `whitson_pvt_sdk.auth` and `HTTPTransport`.

### Package structure

```
whitson_pvt_sdk/
├── __init__.py              # WhitsonPVTClient
├── auth.py                  # ApiToken and credential resolution
├── http.py                  # HTTPTransport (httpx, retries, error mapping)
├── errors.py                # SDKError, ConfigurationError, ResponseError, ...
├── shared/models.py         # hand-maintained shared models
├── shared/pagination.py     # Paginator utility
├── _generated/              # generated models and resource facades
└── v2/                      # public resources and model re-exports
```

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](https://github.com/WhitsonAS/whitson-pvt-sdk/blob/main/LICENSE).

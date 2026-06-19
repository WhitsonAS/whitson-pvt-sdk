# whitson PVT SDK

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

HTTP client for the whitson PVT external API. Python 3.10+.

## Install

```bash
# uv (recommended)
uv add whitson-pvt-sdk

# pip
pip install whitson-pvt-sdk
```

## Quick start

```python
from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.shared.models import ClientCredentials

client = WhitsonPVTClient(
    credentials=ClientCredentials(client_id="...", client_secret="..."),
    base_url="https://internal.pvt.whitson.com",
)

regions = client.regions.list()
well = client.wells.get(well_id=123)
sample = client.samples.get(sample_id=456)
```

Authentication is handled automatically. If you need the same bearer token for an
external integration, use the explicit token helper rather than an auth resource:

```python
token = client.get_access_token()
```

### Retries

The SDK retries transient read failures by default. `GET` requests are attempted up
to 3 times for network timeouts/transport errors and HTTP `408`, `429`, `500`,
`502`, `503`, and `504` responses. Mutating requests (`POST`, `PUT`, and
multipart uploads) are not retried by default.

Retry delays honor `Retry-After`, `retry-after-ms`, and `X-RateLimit-Reset`
headers when present. `X-RateLimit-Limit` and `X-RateLimit-Remaining` are left
available on the raw HTTP response internally, but do not affect retry timing.

Configure retries on the client:

```python
from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.shared.models import ClientCredentials, RetryConfig

client = WhitsonPVTClient(
    credentials=ClientCredentials(client_id="...", client_secret="..."),
    base_url="https://internal.pvt.whitson.com",
    retry_config=RetryConfig(max_attempts=1),  # disables retries
)
```

Configure default request timeouts with `timeout`; downloads and uploads use
`file_timeout`:

```python
client = WhitsonPVTClient(
    credentials=ClientCredentials(client_id="...", client_secret="..."),
    base_url="https://internal.pvt.whitson.com",
    timeout=30.0,
    file_timeout=60.0,
)
```

### Pagination (v2)

v2 list endpoints (regions, projects, fluid models, black oil tables, wells) are
cursor-paginated. Each response includes a `pagination` field:

```python
page = client.regions.list()
for region in page.regions:
    print(region.name)

while page.pagination.next_cursor:
    page = client.regions.list(cursor=page.pagination.next_cursor)
```

Pass `cursor` and `limit` to control pagination:

```python
page = client.regions.list(limit=50)
page = client.regions.list(cursor=page.pagination.next_cursor)
```

Limit defaults to the API default (usually 20) when omitted.

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
just build                       # uv build
just generate v1                 # regenerate v1 models and endpoint wrappers
just generate v2                 # regenerate v2 models and endpoint wrappers
just generate-all                # regenerate both v1 and v2
just all                         # generate-all + lint/format + build
```

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

- `whitson_pvt_sdk/_generated/{version}/models.py`
- `whitson_pvt_sdk/_generated/{version}/{resource}.py`
- `whitson_pvt_sdk/_generated/{version}/resources.py`
- `whitson_pvt_sdk/{version}/models/__init__.py` re-exports generated models
- `whitson_pvt_sdk/{version}/resources.py` re-exports public resource classes

Resource classes expose SDK-shaped method names such as `list`, `get`, `create`,
`update`, `create_bulk`, and `update_bulk`. Lower-level generated module
functions keep OpenAPI operation IDs for traceability.

Authentication endpoints are intentionally excluded from generated resources;
auth is infrastructure owned by `HTTPTransport` and `TokenManager`.

### Package structure

```
whitson_pvt_sdk/
├── __init__.py              # WhitsonPVTClient
├── http.py                  # HTTPTransport (httpx)
├── auth.py                  # TokenManager
├── errors.py                # SDKError, NotFoundError, ...
├── shared/models.py         # hand-maintained shared models
├── _generated/              # generated models, endpoint functions, resource facades
├── v1/                      # public v1 client/resources/model re-exports
└── v2/                      # public v2 client/resources/model re-exports
```

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).

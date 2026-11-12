---
name: whitson-pvt
description: Install and use the Whitson PVT Python SDK and its wpvt command from external Python projects and agent shells. Use when configuring WhitsonPVTClient, connecting an agent to whitson PVT with wpvt mcp, fetching full data that an MCP tool result paged, downsampled or omitted (wpvt api, wpvt samples export), authenticating with an API token (WHITSON_PVT_TOKEN) or a stored wpvt login, checking who is logged in with wpvt auth status, using the API resources, calling regions/wells/samples/projects/fluid models/black-oil tables (BOT)/reports, or working with the SDK's Pydantic request and response models.
---

# Whitson PVT SDK

## Install

Use Python 3.11 or newer.

```bash
uv add whitson-pvt-sdk
```

or:

```bash
pip install whitson-pvt-sdk
```

## Create A Client

Authenticate with an API token. Set `WHITSON_PVT_TOKEN` in the environment (or pass `token=`):

```bash
export WHITSON_PVT_TOKEN=whitson_pvt_...
```

```python
from whitson_pvt_sdk import WhitsonPVTClient

with WhitsonPVTClient(base_url="https://internal.pvt.whitson.com") as client:
    regions = client.regions.list()
```

Leaving the `with` block closes the connections. A long-lived client (a module-level or app-lifetime one) calls `client.close()` at shutdown instead; never call `client._transport.close()`. Closing twice is harmless; a request on a closed client raises `RuntimeError`.

The deployment is `base_url=`, else `WHITSON_PVT_URL`, else the default `wpvt` login. The credential is `token=`, else `WHITSON_PVT_TOKEN`, else the login stored by `wpvt auth login` for that deployment. An API token always wins over a stored login. With none configured, or with the token in use empty, creating the client raises `ConfigurationError`; a stored login the server no longer accepts raises `LoginError`. Tokens start with `whitson_pvt_`; never print or log them, and never read or print the credentials file or keyring entries.

`client.me.get()` returns who the credential belongs to, by `kind`: `api_token` (`user_id`, `name`, `email`, `role`, `scopes`, `token_id`, `token_name`), `user_token` (the same identity fields plus `client_id`) or `legacy_client` (`client_subject`, `full_access`).

## Logins And The wpvt Command

`pip install "whitson-pvt-sdk[cli]"` (or `uv tool install "whitson-pvt-sdk[cli]"`) adds the `wpvt` command; the `mcp` extra, `"whitson-pvt-sdk[mcp]"`, adds `wpvt mcp` as well.

- In scripts, CI and agent sessions, authenticate with `WHITSON_PVT_TOKEN` (and `WHITSON_PVT_URL` for the deployment).
- To check what is configured, run `wpvt auth status --json`. Exit code 0 prints `url`, `credential` (`kind`, `source`) and `identity`; 2 means nothing is configured, 3 means the login is no longer valid or the API rejected the credential, 4 means a network or server error. Errors arrive on stderr as JSON with `error` and `message`.
- Never run `wpvt auth login` from a non-interactive host such as an agent's shell: it waits for a person in a browser. Ask the user to run `wpvt auth login --url <deployment>` in their own terminal (or with `--device` on a machine without a browser, where the deployment enables device login), then check again with `wpvt auth status --json`.
- A login to a `*.pvt.whitson.com` deployment that names whitson's login server needs no confirmation. One that names another login server, or asks for access to any service other than itself (`https://<deployment host>/mcp`), is refused and cannot be overridden: tell the user to report it to whitson. A login to another host (`--trust-host`), or to localhost with another login server or another audience, asks the user to confirm.
- Never pass `--trust-host` or `--yes` to `wpvt auth login`, or `trust_host=True` or an always-yes `confirm=` to `login()`, on your own initiative, and never suggest them to get past a refusal. They decide whether to trust a host outside `*.pvt.whitson.com` and whether to sign in at a login server other than whitson's: those are the user's decisions. Show the user the refusal or the hosts and let them decide.
- A stored login is bound to its deployment URL and is never sent to another one. It renews itself; when it cannot, the error says to log in again.

## Data From The Command Line And MCP

The whitson PVT MCP tools come from `wpvt mcp`, a local stdio server that forwards to the deployment's MCP endpoint with the user's `wpvt` login. The `wpvt` plugin for Claude Code or Codex registers it; without the plugin it is added with `claude mcp add wpvt -- wpvt mcp` or `codex mcp add wpvt -- wpvt mcp`. MCP needs `wpvt auth login`; it refuses API tokens for now.

When the tools are missing or the server failed to start, ask the user to run `wpvt mcp` in a terminal and show you its stderr message (or run `wpvt auth status --json` yourself). The usual causes:

- `wpvt` is not installed or not on `PATH`: the user installs it with `uv tool install "whitson-pvt-sdk[mcp]"`; `wpvt mcp` saying the `mcp` extra is missing needs the same command.
- Not logged in, or the login is no longer valid (`wpvt auth status` exits 2 or 3): ask the user to run `wpvt auth login --url <their deployment>` in their own terminal, then reconnect the server. Never run it yourself.

Working with the data:

- Prefer the MCP tools for lookups and small answers.
- Bulk or full data goes to files through the command line, not through repeated tool calls. When a tool result says the data was paged, downsampled or omitted and carries `full_data` (`{"available_through": "whitsonpvt_cli_and_python_sdk", "method": ..., "path": ...}`), fetch it to a file and work on the file (grep, page, script): `wpvt api METHOD PATH --out FILE` with that exact method and path, or the matching command: `wpvt samples export ID --out DIR` (one directory per sample: `index.json` first, then `sample.json`, `compositions/`, `experiments/`), `wpvt bot export ID --out FILE [--format csv]` for a black-oil table.
- Discover routes with `wpvt api --list --json` and `wpvt api --describe METHOD PATH --json` instead of guessing paths. PATH is relative to `/external/v2`. Add `--paginate` on a paged GET to get every page in one document, `-q KEY=VALUE` for query parameters and `-d @FILE` (or inline JSON, or `-`) for a body; METHOD defaults to GET, or POST with `-d`. Use `jq` on the output; there is no built-in query flag.
- Lists: `wpvt regions list`, `wpvt wells list --region ID`, `wpvt samples list --well ID`, `wpvt projects list --region ID`, `wpvt fluid-models list --project ID`, `wpvt bot list --fluid-model ID` (`bot` is black-oil tables; `black-oil-tables` is an alias), each with `--all --json`; `wpvt <resource> get ID` prints one as JSON.
- Calculations: `wpvt calc flash|saturation-pressure|phase-envelope --input request.json --out result.json`; with `--sample ID --fluid-model ID` the feed comes from the stored sample and the input file leaves out `fluid_model_id` and `feed_composition`.
- Never print, log or paste tokens, and never read the credentials file. Never run `wpvt auth login` yourself, and never pass `--trust-host` or `--yes` on your own.
- Exit codes: 2 usage or configuration, 3 authentication, 4 network or server; errors are on stderr.

In Python, `client.request(method, path, params=..., body=...)` calls any route the same way and returns `status_code`, `headers` and `content`.

SDK 2.x has no client credentials, no `version=` argument and no v1 API. Code that passes `credentials=ClientCredentials(...)` or `version=` needs SDK 1.x.

Do not use `client.authentication`; auth is not exposed as a resource.

## Retries And Timeouts

The SDK retries transient read failures by default. `GET` requests and downloads
retry `408`, `429`, `500`, `502`, `503`, and `504`. Mutating requests (`POST`,
`PUT`, `PATCH`, `DELETE`, and multipart uploads) are not retried by default, except for HTTP `429`
rate-limit responses.

Retry timing honors `Retry-After`, `retry-after-ms`, and `X-RateLimit-Reset`
headers when present.

Configure retries and timeouts on `WhitsonPVTClient`:

```python
from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.shared.models import RetryConfig

client = WhitsonPVTClient(
    base_url="https://internal.pvt.whitson.com",
    retry_config=RetryConfig(max_attempts=3),
    timeout=30.0,
    file_timeout=60.0,
)
```

Use `RetryConfig(max_attempts=1)` to disable retries. `max_attempts` includes
the first request. `RetryConfig.methods` controls non-429 retries only; remove
`429` from `RetryConfig.statuses` to disable all-method rate-limit retries. If
all retries are exhausted on HTTP `429`, the SDK raises `RateLimitError` with
`retry_after_seconds` when retry timing headers are present.

## Errors

Everything the SDK raises derives from `SDKError`; import the classes from `whitson_pvt_sdk.errors`.

- `ConfigurationError`: no usable token when the client is created. No HTTP fields.
- `NoResponseError`: the request got no response (connection error, timeout) after retries. No HTTP fields.
- `ResponseError`: the API answered with an error status; always has `status_code: int`, plus `response_body` and `request_id`. Subclasses: `AuthError` (401/403), `NotFoundError` (404), `ValidationError` (400/422), `RateLimitError` (429, with `retry_after_seconds`) and `APIError` (any other status).
- `CalculationError`: a calculation returned a failed result (`code`, `sample_id`, `input_index`, `error`).

Catch `AuthError` only for a rejected token; a missing token is `ConfigurationError`.

## Common Resource Calls

Access resources from the client:

```python
regions = client.regions.list(limit=100)
region = client.regions.get(region_id=123)

wells = client.wells.list(region_id=123, limit=100)
well = client.wells.get(well_id=456)

samples = client.samples.list(well_id=456)
sample = client.samples.get(sample_id=789)

projects = client.projects.list(region_id=123, limit=100)
project = client.projects.get(project_id=321)

fluid_models = client.fluid_models.list(project_id=321, limit=100)
fluid_model = client.fluid_models.get(fluid_model_id=654)

black_oil_tables = client.black_oil_tables.list(fluid_model_id=654, limit=100)
black_oil_table = client.black_oil_tables.get(black_oil_table_id=987)
```

For paginated list endpoints, use `iterate()` for lazy traversal or
`list_all()` for eager collection. Pass `limit=<int>` to control page size.

## Pagination

List endpoints (regions, wells, projects, fluid models, black oil tables)
return a `pagination: PaginationMeta` field with `next_cursor` and `prev_cursor`.
Use the generated helpers for most callers:

```python
for region in client.regions.iterate(limit=50):
    print(region.name)

all_wells = client.wells.list_all(region_id=123, limit=50)
```

When manual cursor control is needed, call `list()` directly and follow
`next_cursor`:

```python
page = client.regions.list(limit=50)
page2 = client.regions.list(cursor=page.pagination.next_cursor, limit=50)
```

Passing `limit` sets the page size (1–250). When omitted, the API default applies (usually 20).
All five resources support `name=` for a case-insensitive exact match, including
`iterate()` and `list_all()`.

## Creating And Updating Data

Use generated Pydantic models from `whitson_pvt_sdk.v2.models` for create and update requests.

```python
from whitson_pvt_sdk.v2.models import CreateRegionModel, UpdateRegionModel

created = client.regions.create(
    CreateRegionModel(
        name="New region",
        region_type="asset",
        reservoir_type="Conventional",
    )
)
updated = client.regions.update(
    region_id=created.id,
    data=UpdateRegionModel(name="Renamed region"),
)
```

Use the SDK methods instead of manually constructing HTTP requests. Returned values are Pydantic response models, so callers can use normal attribute access and `model_dump()` when they need dictionaries.

## Reports

Report export returns zip bytes and a synthetic filename:

```python
archive_data, filename = client.reports.export(report_id=123)
```

Prefer `client.import_sessions` for new archive workflows: `create`, `get`,
`list_records`, `update_resolution`, `commit`, and `delete`. Creation accepts ZIP
bytes and `ImportSessionCreateOptionsModel`. Review records before committing;
pass explicit `selected_record_ids` in `ImportCommitRequestModel` to avoid committing
all eligible records. Deleting a session does not undo committed native entities.
Use `client.import_records` for individual OSDU records.

Export OSDU archives with `client.reports.export(report_id=123, format="osdu")`.

Legacy report import and preflight accept zip bytes. Pass `ImportArchiveOptions` when import options are needed:

```python
from pathlib import Path

from whitson_pvt_sdk.shared.models import ImportArchiveOptions

archive_data = Path("archive.zip").read_bytes()

preflight = client.reports.preflight_import(
    archive_data,
    options=ImportArchiveOptions(region_id=123),
)

result = client.reports.import_archive(
    archive_data,
    options=ImportArchiveOptions(
        region_id=123,
        acknowledge_suggestions=True,
    ),
)
```

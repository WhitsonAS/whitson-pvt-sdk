---
name: whitson-pvt
description: Install and use the Whitson PVT Python SDK and its wpvt command from external Python projects and agent shells. Use when configuring WhitsonPVTClient, connecting an agent to whitson PVT with wpvt mcp, fetching full data that an MCP tool result paged, downsampled or omitted (wpvt api, wpvt samples export), answering aggregate questions (counts, averages, summaries or exports across a region, project or many wells) with one script instead of many tool calls, authenticating with an API token (WHITSON_PVT_TOKEN) or a stored wpvt login, checking who is logged in with wpvt auth status, reading wpvt exit codes and JSON errors, using the API resources, calling regions/wells/samples/projects/fluid models/black-oil tables (BOT)/reports, or working with the SDK's Pydantic request and response models.
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

`"whitson-pvt-sdk[cli]"` adds the `wpvt` command and `"whitson-pvt-sdk[mcp]"` adds `wpvt mcp` as well; install either with `uv tool install` or `pip install`.

## Create A Client

```python
from whitson_pvt_sdk import WhitsonPVTClient

with WhitsonPVTClient() as client:
    regions = client.regions.list()
```

The deployment is `base_url=`, else `WHITSON_PVT_URL`, else the default `wpvt` login. The credential is `token=`, else `WHITSON_PVT_TOKEN`, else the login stored by `wpvt auth login` for that deployment. An API token always wins over a stored login, but is only sent to a URL given explicitly (`base_url=` or `WHITSON_PVT_URL`), so a token can never leak to whatever the default login happens to be; with only the token set, the client raises `ConfigurationError`. API tokens start with `whitson_pvt_`.

Leaving the `with` block closes the connections; a long-lived client calls `client.close()` at shutdown instead.

`client.me.get()` returns who the credential belongs to; its `kind` says which identity shape you got.

## Logins

- In scripts, CI and agent sessions, authenticate with `WHITSON_PVT_TOKEN` and name the deployment with `WHITSON_PVT_URL` (data commands have no `--url`; only `wpvt auth` and `wpvt mcp` take it).
- `wpvt auth status --json` shows what is configured: the deployment `url`, the `credential` (`kind`, `source`) and the `identity`. Its exit code tells you what is wrong (see Exit Codes And Errors).
- `wpvt auth login` waits for a person in a browser, so it cannot finish from an agent's shell. Ask the user to run `wpvt auth login --url <deployment>` in their own terminal (`--device` on a machine without a browser, where the deployment allows it), then check again with `wpvt auth status --json`.
- A login to a `*.pvt.whitson.com` deployment that names whitson's login server needs no confirmation. One that names another login server, or asks for access to a service other than the deployment's own `/mcp`, is refused with no override: tell the user to report it to whitson. Other hosts ask the user to confirm.
- `--trust-host` and `--yes` on `wpvt auth login` (and `trust_host=True` or an always-yes `confirm=` on `login()`) decide whether to trust a host and a login server. Those are the user's decisions, so never pass them on your own or suggest them to get past a refusal; show the user the refusal and let them decide.
- A stored login is bound to its deployment URL, renews itself, and says when it needs a new login.
- Never print, log or paste tokens, and never read the credentials file or keyring entries.

## MCP And The Command Line

The whitson PVT MCP tools come from `wpvt mcp`, a local stdio server that forwards to the deployment's MCP endpoint with the user's `wpvt` login (it does not accept API tokens). The `wpvt` plugin for Claude Code or Codex registers it; without the plugin, `claude mcp add wpvt -- wpvt mcp` or `codex mcp add wpvt -- wpvt mcp`.

When the tools are missing or the server failed to start, run `wpvt auth status --json`, or ask the user to run `wpvt mcp` in a terminal and show you its stderr. Usually `wpvt` is not installed or not on `PATH` (the user installs the `mcp` extra), or the login is missing or no longer valid (the user runs `wpvt auth login`). When the message carries the deployment's own reason instead of suggesting a login, relay that reason: a new login may not fix it.

Working with the data:

- Prefer the MCP tools for lookups and small answers; for counts, averages and summaries over many records, see Aggregate Questions.
- Bulk or full data goes to files through the command line. When a tool result says the data was paged, downsampled or omitted and carries `full_data` with a `method` and `path`, fetch it with `wpvt api METHOD PATH --out FILE` and work on the file (grep, page, script). `wpvt samples export ID --out DIR` writes one directory per sample, with `index.json` to read first; `wpvt bot export` writes a black-oil table, and `wpvt calc` runs a calculation from a JSON request (see their `--help`).
- Discover instead of guessing: `wpvt --help` and `wpvt <group> --help` for commands and options, `wpvt api --list --json` for routes, `wpvt api --describe METHOD PATH --json` for a route's parameters, schemas and required scopes. PATH is relative to `/external/v2`. `wpvt api` takes `--paginate` (every page in one document), `-q KEY=VALUE` and `-d` for a body; there is no query flag, so use `jq` on the output.
- Resource groups have `list` and `get`; `list --all --json` prints one document with `items` and `next_cursor`.

In Python, `client.request(method, path, params=..., body=...)` calls any route and returns `status_code`, `headers` and `content`.

This SDK has no client credentials, no `version=` argument and no v1 API; code that passes `credentials=ClientCredentials(...)` or `version=` was written for SDK 1.x. Auth is not a resource: do not use `client.authentication`.

## Exit Codes And Errors

`wpvt` prints data alone on stdout and errors on stderr. Exit codes: 0 success, 1 any other error (such as a busy credential store: try again), 2 usage or configuration (nothing configured, a token without a URL), 3 authentication (the login is no longer valid or the API rejected the credential), 4 network or server (including any other HTTP error, 404 too).

With `--json`, the error is one JSON object on stderr with `error` (`configuration`, `authentication`, `network`, `server` or `error`) and `message`. When the API answered, it also has `status`, the HTTP status code, and `request_id` (`null` if the server sent none); a network failure has neither. Use `status` to tell a missing record (404) from a rejected request (422) or a server fault (5xx), and give the user the `request_id` when they need to contact support.

## Aggregate Questions

Counts, averages and per-record summaries across a region or project touch many records. Answer them with one script against the SDK, or one `wpvt api ... | jq` pipeline, rather than one MCP tool call per record: the script reads every page, aggregates, and prints only the answer, so the records never enter your context. A question that a few tool calls answer stays with MCP.

- Find the routes first (`wpvt api --list`). When no route lists what you need across a parent, page through the parents and read each one once.
- Every number's unit is a sibling field, `<value>_unit` (an experiment's values share the experiment's units). Stored values come back in the unit they were entered in; no read route converts them. Group by unit and carry it into the answer. If the units differ, say so and either report per unit or ask the user how to convert; do not convert with constants you assume. Calculation requests are different: they take `output_unit_system` for their results (see `wpvt api --describe`).
- Print the answer, not the data. To look at records, write them to a file and inspect a few.
- A non-zero exit means the answer is incomplete: report the error, not the partial output.

For example, the mean `reservoir_pressure` of each well's samples in one region, per unit. Run it with the Python that has the SDK installed; it uses the same `WHITSON_PVT_URL` and `WHITSON_PVT_TOKEN` (or stored login) as `wpvt`.

```python
import os
from collections import defaultdict
from statistics import mean

from whitson_pvt_sdk import WhitsonPVTClient

values = defaultdict(list)
with WhitsonPVTClient() as client:
    for well in client.wells.iterate(region_id=int(os.environ["REGION_ID"]), limit=250):
        for sample in client.samples.list(well.id).samples:
            if sample.reservoir_pressure is not None:
                key = (well.id, well.name, sample.reservoir_pressure_unit)
                values[key].append(sample.reservoir_pressure)
for (well_id, name, unit), found in values.items():
    print(f"{well_id} {name}: {mean(found):.4g} {unit} from {len(found)} samples")
```

The same with the command line:

```bash
set -o pipefail
wpvt api "/regions/$REGION_ID/wells" -q limit=250 --paginate | jq -r '.wells[].id' |
  while read -r id; do wpvt api "/wells/$id" || exit; done |
  jq -rs '.[] | . as $well | [.samples[]? | select(.reservoir_pressure != null)]
    | group_by(.reservoir_pressure_unit)[]
    | "\($well.id) \($well.name): \(map(.reservoir_pressure) | add / length) \(.[0].reservoir_pressure_unit) from \(length) samples"'
```

## Retries And Timeouts

`GET` requests and downloads retry transient failures (timeouts, rate limits, gateway and server errors); other methods (`POST`, `PUT`, `PATCH`, `DELETE`, uploads) retry only a rate limit (`429`), so a write is never sent twice. Waits honour the server's retry headers. Configure retries and timeouts on the client:

```python
from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.shared.models import RetryConfig

client = WhitsonPVTClient(retry_config=RetryConfig(max_attempts=3), timeout=30.0, file_timeout=60.0)
```

`max_attempts` includes the first request, so `RetryConfig(max_attempts=1)` disables retries. When retries run out on `429`, the SDK raises `RateLimitError`, with `retry_after_seconds` when the server gave a delay.

## Errors

Everything the SDK raises derives from `SDKError`; import the classes from `whitson_pvt_sdk.errors`.

- `ConfigurationError`: no usable deployment URL or token when the client is created. No HTTP fields.
- `LoginError`: the stored login is no longer valid; ask the user to run `wpvt auth login`.
- `NoResponseError`: the request got no response (connection error, timeout) after retries. No HTTP fields.
- `ResponseError`: the API answered with an error status; always has `status_code`, plus `response_body` and `request_id`. Subclasses: `AuthError` (401/403), `NotFoundError` (404), `ValidationError` (400/422), `RateLimitError` (429) and `APIError` (any other status).
- `CalculationError`: a calculation returned a failed result (`code`, `sample_id`, `input_index`, `error`).
- `MissingDataError`: the input names data that does not exist, such as a sample without an adjusted composition in the fluid model.

Catch `AuthError` only for a rejected token; a missing token is `ConfigurationError`.

## Resources And Pagination

Resources hang off the client (`client.regions`, `client.wells`, `client.samples`, `client.projects`, `client.fluid_models`, `client.black_oil_tables`, `client.reports`, ...). Each has `get(<resource>_id)`; a listed resource has `list(<parent>_id, ...)`, which returns one page (`pagination.next_cursor`), plus `iterate()` for lazy traversal and `list_all()` for eager collection. `limit=` sets the page size and `name=` filters by case-insensitive exact name. `client.samples.list(well_id)` is the exception: it returns all of a well's samples at once.

```python
for well in client.wells.iterate(region_id=region_id, limit=100):
    print(well.id, well.name)
```

Returned values are Pydantic models: use attribute access, and `model_dump()` when you need a dictionary. Prefer the SDK methods over hand-built HTTP requests.

## Creating And Updating Data

Create and update requests take the generated models from `whitson_pvt_sdk.v2.models` (`CreateRegionModel`, `UpdateRegionModel`, ...): `client.regions.create(CreateRegionModel(...))`, `client.regions.update(region_id=..., data=UpdateRegionModel(...))`. The model's fields and `Literal` types are the required fields and allowed values; read them from the model, or from `wpvt api --describe POST /regions --json`, rather than guessing.

## Reports

`client.reports.export(report_id=...)` returns zip bytes and a synthetic filename; `format="osdu"` exports an OSDU archive.

For importing archives, prefer `client.import_sessions` (`create`, `get`, `list_records`, `update_resolution`, `commit`, `delete`): creation takes ZIP bytes and `ImportSessionCreateOptionsModel`. Review the records before committing, and pass explicit `selected_record_ids` in `ImportCommitRequestModel` so only what you reviewed is committed. Deleting a session does not undo committed entities. `client.import_records` handles individual OSDU records.

The legacy `client.reports.preflight_import(data, options=...)` and `client.reports.import_archive(data, options=...)` take zip bytes and `ImportArchiveOptions` (from `whitson_pvt_sdk.shared.models`).

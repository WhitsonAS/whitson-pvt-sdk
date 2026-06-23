# whitson PVT SDK — Examples

Self-contained scripts demonstrating common use of the whitson PVT SDK.

License: [Apache-2.0](https://github.com/WhitsonAS/whitson-pvt-sdk/blob/main/LICENSE)

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)

```bash
uv sync
```

## Configuration

All examples read credentials from environment variables. Start from the example
env file, edit the values, then source it before running examples:

```bash
cp .env.example .env
$EDITOR .env
source .env
uv run examples/basic_connect.py
```

## Examples

| File                                  | Description                                        | Command                                                 |
| ------------------------------------- | -------------------------------------------------- | ------------------------------------------------------- |
| `basic_connect.py`                    | Connect, list regions, and iterate pagination      | `uv run examples/basic_connect.py`                      |
| `basic_crud.py`                       | Create, read, update a region with Pydantic models | `uv run examples/basic_crud.py`                         |
| `flash_calculation.py`                | Run a v2 flash calculation                         | `uv run examples/flash_calculation.py`                  |
| `saturation_pressure_calculation.py`  | Run a v2 saturation pressure calculation           | `uv run examples/saturation_pressure_calculation.py`    |
| `separator_process_calculation.py`    | Run a v2 separator process calculation             | `uv run examples/separator_process_calculation.py`      |
| `report_import.py`                    | Export a report archive and import with preflight  | `uv run examples/report_import.py`                      |
| `multi_domain_copy.py`                | Copy reports from multiple source domains          | `uv run examples/multi_domain_copy.py config.json`      |
| `pagination.py`                       | Walk all pages of a v2 paginated endpoint          | `uv run examples/pagination.py`                         |
| `cli_list.py`                         | argparse CLI for listing resources                 | `uv run examples/cli_list.py regions`                   |
| `fastapi_demo.py`                     | FastAPI app with SDK-backed routes                 | `uv run examples/fastapi_demo.py`                       |

## Pagination (v2)

v2 list endpoints return a `PaginationMeta` field (`next_cursor`, `prev_cursor`).
Pass `cursor` and `limit` to `list()` methods:

```python
page = client.regions.list(limit=50)
print(page.pagination.next_cursor)  # "abc123" or None

page2 = client.regions.list(cursor=page.pagination.next_cursor)
```

The `pagination.py` example shows how to collect all pages into a single list.

Limit defaults to the API default (usually 20) when omitted. Valid range: 1-250.

## Authentication Token

The SDK handles bearer auth automatically through the external API token endpoint.
For integrations that need the same token outside SDK resource methods, use:

```python
token = client.get_access_token()
```

Auth is not exposed as a resource like `client.authentication`; it is an SDK
transport concern.

## Retries And Timeouts

The SDK retries transient read failures by default. Retries apply to `GET`
requests and downloads only, not writes or multipart uploads. Retry timing honors
`Retry-After`, `retry-after-ms`, and `X-RateLimit-Reset` headers when present.

Configure retry attempts and timeouts on the client:

```python
from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.shared.models import ClientCredentials, RetryConfig

client = WhitsonPVTClient(
    credentials=ClientCredentials(client_id="...", client_secret="..."),
    base_url="https://internal.pvt.whitson.com",
    retry_config=RetryConfig(max_attempts=3),
    timeout=30.0,
    file_timeout=60.0,
)
```

Use `RetryConfig(max_attempts=1)` to disable retries.

For the FastAPI example, install the extra dependency first:

```bash
uv add fastapi uvicorn
```

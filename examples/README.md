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

## Calculation Feed Compositions

Calculation inputs such as flash, saturation pressure, and separator process need
`feed_composition` values. Use the v2 calculation helpers to get them from sample
ids instead of building component lists by hand:

```python
feed_composition = client.calculations.get_sample_feed_composition(
    fluid_model_id=123,
    sample_id=456,
    source="slate_to_slate_converted",
)
```

For multiple samples, use the dict keyed by sample id:

```python
feed_compositions = client.calculations.get_sample_feed_compositions(
    fluid_model_id=123,
    sample_ids=[456, 789],
    source="adjusted_compositions",
)
feed_composition = feed_compositions[456]
```

Valid composition sources are `"slate_to_slate_converted"` and
`"adjusted_compositions"`.

## JSON Output Utilities

Use `print_json` or `write_json` for readable SDK responses:

```python
from whitson_pvt_sdk.utils import print_json, write_json

print_json(response)
path = write_json(response, "flash_response.json")
```

`write_json(response)` writes to `output.json` in the current directory. If the
target exists, it writes the next available path such as `output_1.json` or
`flash_response_1.json`. To intentionally replace an existing file, pass
`overwrite=True`:

```python
write_json(response, "flash_response.json", overwrite=True)
```

## Errors And Logging

All SDK exceptions inherit from `SDKError`. HTTP failures include structured
metadata when available: `status_code`, `response_body`, and `request_id`.
Calculation result failures raised by SDK helpers use `CalculationError`, which
includes `code`, `sample_id`, `input_index`, and the original API error model.

```python
from whitson_pvt_sdk.errors import CalculationError, SDKError

try:
    feed_composition = client.calculations.get_sample_feed_composition(
        fluid_model_id=123,
        sample_id=456,
    )
except CalculationError as exc:
    print(f"Calculation failed for sample {exc.sample_id}: {exc.message}")
except SDKError as exc:
    print(f"SDK error: {exc.message}")
```

The SDK uses the `whitson_pvt_sdk` logger and does not configure global logging.
Enable debug logs in applications when diagnosing retries or API failures:

```python
import logging

logging.basicConfig(level=logging.INFO)
logging.getLogger("whitson_pvt_sdk").setLevel(logging.DEBUG)
```

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

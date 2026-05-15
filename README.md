# whitson PVT SDK

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
from whitson_pvt_sdk.models import ClientCredentials

v1 = WhitsonPVTClient(
    credentials=ClientCredentials(client_id="...", client_secret="..."),
    base_url="https://internal.pvt.whitson.com",
    version="v1",
)

regions = v1.regions.list()
well = v1.wells.get(well_id=123)
sample = v1.samples.get(sample_id=456)
```

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
```

### Tasks

```bash
just lint                        # ruff check
just format                      # ruff format
just build                       # uv build
just generate v1                 # regenerate v1 models from OpenAPI
just generate v2                 # regenerate v2 models from OpenAPI
just generate-all                # regenerate both v1 and v2
just all                         # generate-all + lint/format + build
```

### Model generation

Models in `models/v1/_generated.py` and `models/v2/_generated.py` are generated from the live API's OpenAPI spec:

This fetches `/external/{version}/docs/openapi.json` from the configured `BASE_URL` and runs `datamodel-code-generator`.

### Package structure

```
whitson_pvt_sdk/
├── __init__.py              # WhitsonPVTClient
├── http.py                  # HTTPTransport (httpx)
├── auth.py                  # TokenManager
├── errors.py                # SDKError, NotFoundError, ...
├── models/
│   ├── v1/_generated.py      # auto-generated from /external/v1/docs/openapi.json
│   ├── v2/_generated.py      # auto-generated from /external/v2/docs/openapi.json
│   └── manual.py             # hand-maintained models (ClientCredentials, multipart)
├── v1/                      # v1 resources (typed classes + plain HTTP functions)
└── v2/                      # v2 resources (paginated models where diverged)
```

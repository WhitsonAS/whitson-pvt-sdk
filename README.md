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

client = WhitsonPVTClient(
    credentials=ClientCredentials(client_id="...", client_secret="..."),
    base_url="https://api.whitson.com",
)

regions = client.regions.list()
well = client.wells.get(well_id=123)
sample = client.samples.get(sample_id=456)
```

## Development

### Prerequisites

- **[uv](https://docs.astral.sh/uv/)** — Python package & project manager
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

### Setup

```bash
uv sync                          # installs Python deps + dev tools
uv tool install rust-just         # installs just (command runner) globally
```

### Tasks

```bash
just lint                        # ruff check
just format                      # ruff format
just build                       # uv build
just generate-models             # fetch OpenAPI spec + regenerate models/_generated.py
just all                         # generate-models + lint/format + build
```

just build # uv build
just all # sync + generate + lint/format + build

````

### Model generation

Models in `whitson_pvt_sdk/models/_generated.py` are generated from the live API's OpenAPI spec:

```bash
just generate-models
````

This fetches `/external/v1/docs/openapi.json` from the configured `OPENAPI_URL` and runs `datamodel-code-generator`.

### Package structure

```
whitson_pvt_sdk/
├── __init__.py         # WhitsonPVTClient
├── http.py             # HTTPTransport (httpx)
├── auth.py             # TokenManager (token exchange + cache)
├── errors.py           # SDKError, NotFoundError, AuthError, etc.
├── models/
│   ├── _generated.py   # auto-generated from OpenAPI
│   ├── _manual.py       # hand-maintained multipart models
│   └── __init__.py
└── v1/                 # resource modules (regions, wells, samples, ...)
```

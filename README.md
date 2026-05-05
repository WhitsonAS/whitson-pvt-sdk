# whitson PVT SDK

HTTP client for the whitson PVT external API. Python 3.10+.

## Install

```bash
# uv (recommended)
uv add pvt-sdk

# pip
pip install pvt-sdk
```

## Quick start

```python
from pvt_sdk import WhitsonPVTClient
from pvt_sdk._models import ClientCredentials

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

- **[just](https://github.com/casey/just)** — command runner

  ```bash
  # any of:
  cargo install just       # via Cargo (Rust)
  brew install just        # macOS
  curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/.local/bin
  ```

- **[datamodel-code-generator](https://koxudxi.github.io/datamodel-code-generator/)** — OpenAPI → Pydantic models

  ```bash
  uv tool install datamodel-code-generator
  ```

### Setup

```bash
just sync           # uv sync
just install-tools  # install datamodel-code-generator
```

### Tasks

```bash
just generate-models   # fetch OpenAPI spec + regenerate _models/_generated.py
just lint              # ruff check
just format            # ruff format
just build             # uv build
just all               # sync + generate + lint/format + build
```

### Model generation

Models in `src/pvt_sdk/_models/_generated.py` are generated from the live API's OpenAPI spec:

```bash
just generate-models
```

This fetches `/external/v1/docs/openapi.json` from the configured `OPENAPI_URL` and runs `datamodel-code-generator`.

### Package structure

```
src/pvt_sdk/
├── __init__.py         # WhitsonPVTClient
├── http.py             # HTTPTransport (httpx)
├── auth.py             # TokenManager (token exchange + cache)
├── errors.py           # SDKError, NotFoundError, AuthError, etc.
├── _models/
│   ├── _generated.py   # auto-generated from OpenAPI
│   ├── _manual.py       # hand-maintained multipart models
│   └── __init__.py
└── v1/                 # resource modules (regions, wells, samples, ...)
```

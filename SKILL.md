---
name: whitson-pvt-sdk
description: Install and use the Whitson PVT Python SDK from external Python projects. Use when configuring WhitsonPVTClient, authenticating with ClientCredentials, using v2 API resources, calling regions/wells/samples/projects/fluid models/black oil tables/reports, or working with the SDK's Pydantic request and response models.
---

# Whitson PVT SDK

## Install

Use Python 3.10 or newer.

```bash
uv add whitson-pvt-sdk
```

or:

```bash
pip install whitson-pvt-sdk
```

## Create A Client

Import the public client and credential model:

```python
from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.shared.models import ClientCredentials

client = WhitsonPVTClient(
    credentials=ClientCredentials(
        client_id="...",
        client_secret="...",
    ),
    base_url="https://internal.pvt.whitson.com",
)
```

The SDK defaults to `version="v2"`. Do not pass `version` unless a different API version is explicitly needed. Use `version="v1"` only for legacy compatibility; v1 is deprecated and expected to be removed soon.

Pass `auth0_domain` or `audience` only when the deployment requires non-default Auth0 settings:

```python
client = WhitsonPVTClient(
    credentials=ClientCredentials(client_id="...", client_secret="..."),
    base_url="https://internal.pvt.whitson.com",
    auth0_domain="...",
    audience="...",
)
```

Authentication is handled automatically. If a caller needs the same bearer token
for a non-SDK integration, use the explicit helper:

```python
token = client.get_access_token()
```

Do not use `client.authentication`; auth is not exposed as a resource.

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

For paginated v2 list endpoints, pass `cursor=page.pagination.next_cursor` to fetch the next page and `limit=<int>` to control page size.

## Pagination

v2 list endpoints (regions, wells, projects, fluid models, black oil tables) return a
`pagination: PaginationMeta` field with `next_cursor` and `prev_cursor`.
Iterate pages by following `next_cursor`:

```python
page = client.regions.list(limit=50)

for region in page.regions:
    print(region.name)

while page.pagination.next_cursor:
    page = client.regions.list(cursor=page.pagination.next_cursor)
    for region in page.regions:
        print(region.name)
```

Passing `limit` sets the page size (1–250). When omitted, the API default applies (usually 20).

## Creating And Updating Data

Use generated Pydantic models from the selected API version for create and update requests.

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

For legacy `version="v1"` usage, import request models from `whitson_pvt_sdk.v1.models`.

Use the SDK methods instead of manually constructing HTTP requests. Returned values are Pydantic response models, so callers can use normal attribute access and `model_dump()` when they need dictionaries.

## Reports

Report export returns zip bytes and a synthetic filename:

```python
archive_data, filename = client.reports.export(report_id=123)
```

Report import and preflight accept zip bytes. Pass `ExternalImportArchiveOptions` when import options are needed:

```python
from pathlib import Path

from whitson_pvt_sdk.shared.models import ExternalImportArchiveOptions

archive_data = Path("archive.zip").read_bytes()

preflight = client.reports.preflight_import(
    archive_data,
    options=ExternalImportArchiveOptions(region_id=123),
)

result = client.reports.import_archive(
    archive_data,
    options=ExternalImportArchiveOptions(
        region_id=123,
        acknowledge_suggestions=True,
    ),
)
```

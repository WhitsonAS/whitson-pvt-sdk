# whitson PVT SDK — Examples

Self-contained scripts demonstrating common use of the whitson PVT SDK.

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)

```bash
uv sync
```

## Configuration

All examples read credentials from environment variables. Set these before running:

```bash
export WHITSON_CLIENT_ID="your-client-id"
export WHITSON_CLIENT_SECRET="your-client-secret"
export WHITSON_BASE_URL="https://internal.pvt.whitson.com"  # optional, defaults to this
```

## Examples

| File | Description | Command |
|---|---|---|
| `basic_connect.py` | Connect, list regions, iterate pagination | `uv run examples/basic_connect.py` |
| `basic_crud.py` | Create, read, update a region with Pydantic models | `uv run examples/basic_crud.py` |
| `basic_reports.py` | Export a report to file, import/preflight | `uv run examples/basic_reports.py` |
| `pagination.py` | Walk all pages of a v2 paginated endpoint | `uv run examples/pagination.py` |
| `cli_list.py` | argparse CLI for listing resources | `uv run examples/cli_list.py regions` |
| `fastapi_demo.py` | FastAPI app with SDK-backed routes | `uv run examples/fastapi_demo.py` |

For the FastAPI example, install the extra dependency first:

```bash
uv add fastapi uvicorn
```

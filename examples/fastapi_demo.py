"""FastAPI app backed by the whitson PVT SDK.

Demonstrates:
- Lifespan context manager for SDK client lifecycle
- Routes that proxy to SDK resource methods
- Error mapping from SDKError to HTTPException
- v2 pagination cursor support

Install extra dependencies before running:
    uv add fastapi uvicorn

Usage:
    uv run examples/fastapi_demo.py
    # then open http://localhost:8000/regions
"""

import os
from contextlib import asynccontextmanager
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.errors import AuthError, NotFoundError, SDKError
from whitson_pvt_sdk.shared.models import ClientCredentials
from whitson_pvt_sdk.v2 import WhitsonPVTClientV2

_client: WhitsonPVTClientV2 | None = None

load_dotenv()


def get_client() -> WhitsonPVTClientV2:
    assert _client is not None
    return _client


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _client
    _client = WhitsonPVTClient(
        credentials=ClientCredentials(
            client_id=os.environ["WHITSON_CLIENT_ID"],
            client_secret=os.environ["WHITSON_CLIENT_SECRET"],
        ),
        base_url=os.environ.get("WHITSON_BASE_URL", "https://internal.pvt.whitson.com"),
    )
    yield
    _client = None


app = FastAPI(lifespan=lifespan)


@app.get("/regions")
def list_regions(
    client: Annotated[WhitsonPVTClientV2, Depends(get_client)],
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None),
):
    try:
        page = client.regions.list(cursor=cursor, limit=limit)
        return {
            "regions": [r.model_dump() for r in page.regions],
            "next_cursor": page.pagination.next_cursor,
            "prev_cursor": page.pagination.prev_cursor,
        }
    except SDKError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/regions/{region_id}")
def get_region(region_id: int, client: Annotated[WhitsonPVTClientV2, Depends(get_client)]):
    try:
        region = client.regions.get(region_id)
        return region.model_dump()
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Region not found")
    except AuthError:
        raise HTTPException(status_code=401, detail="Authentication failed")
    except SDKError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/regions/{region_id}/wells")
def list_wells(
    region_id: int,
    client: Annotated[WhitsonPVTClientV2, Depends(get_client)],
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None),
):
    try:
        page = client.wells.list(region_id, cursor=cursor, limit=limit)
        return {
            "wells": [w.model_dump() for w in page.wells],
            "next_cursor": page.pagination.next_cursor,
            "prev_cursor": page.pagination.prev_cursor,
        }
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Region not found")
    except SDKError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/regions/{region_id}/projects")
def list_projects(
    region_id: int,
    client: Annotated[WhitsonPVTClientV2, Depends(get_client)],
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None),
):
    try:
        page = client.projects.list(region_id, cursor=cursor, limit=limit)
        return {
            "projects": [p.model_dump() for p in page.projects],
            "next_cursor": page.pagination.next_cursor,
            "prev_cursor": page.pagination.prev_cursor,
        }
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Region not found")
    except SDKError as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("__main__:app", host="0.0.0.0", port=8000, reload=True)

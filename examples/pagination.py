"""Walk all pages of a v2 paginated endpoint.

Demonstrates:
- Generic cursor-based pagination for any paginated resource
- Fetching all regions and all projects across pages
- Practical pattern for building a full local copy
"""

import os

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.models.manual import ClientCredentials
from whitson_pvt_sdk.v2 import WhitsonPVTClientV2


def collect_all_regions(client: WhitsonPVTClientV2, limit: int = 100) -> list:
    all_regions = []
    cursor = None

    while True:
        page = client.regions.list(cursor=cursor, limit=limit)
        all_regions.extend(page.regions)
        cursor = page.pagination.next_cursor
        if not cursor:
            break

    return all_regions


def collect_all(client, list_method, collection_attr: str, limit: int = 100) -> list:
    all_items = []
    cursor = None

    while True:
        page = list_method(cursor, limit)
        all_items.extend(getattr(page, collection_attr))
        cursor = page.pagination.next_cursor
        if not cursor:
            break

    return all_items


def main() -> None:
    client = WhitsonPVTClient(
        credentials=ClientCredentials(
            client_id=os.environ["WHITSON_CLIENT_ID"],
            client_secret=os.environ["WHITSON_CLIENT_SECRET"],
        ),
        base_url=os.environ.get("WHITSON_BASE_URL", "https://internal.pvt.whitson.com"),
    )

    regions = collect_all_regions(client)
    print(f"Collected {len(regions)} regions total")

    for region in regions[:5]:
        print(f"  - {region.name} (id={region.id})")
        wells = collect_all(
            client,
            lambda cursor, limit, rid=region.id: client.wells.list(
                rid, cursor=cursor, limit=limit
            ),
            "wells",
        )
        print(f"    {len(wells)} wells")
        projects = collect_all(
            client,
            lambda cursor, limit, rid=region.id: client.projects.list(
                rid, cursor=cursor, limit=limit
            ),
            "projects",
        )
        print(f"    {len(projects)} projects")


if __name__ == "__main__":
    main()

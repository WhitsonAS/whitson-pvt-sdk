"""Walk all pages of a v2 paginated endpoint.

Demonstrates:
- Generic cursor-based pagination for any paginated resource
- Fetching all regions, wells, and projects across pages
- Practical pattern for building a full local copy
"""

import os

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.models.manual import ClientCredentials
from whitson_pvt_sdk.v2 import WhitsonPVTClientV2


def collect_all_regions(client: WhitsonPVTClientV2, limit: int = 100) -> list:
    all_regions = []
    page = client.regions.list(limit=limit)

    while True:
        all_regions.extend(page.regions)
        if not page.pagination.next_cursor:
            break
        page = client.regions.list(cursor=page.pagination.next_cursor, limit=limit)

    return all_regions


def collect_all(list_method, collection_attr: str, limit: int = 100) -> list:
    all_items = []
    page = list_method(None, limit)

    while True:
        all_items.extend(getattr(page, collection_attr))
        if not page.pagination.next_cursor:
            break
        page = list_method(page.pagination.next_cursor, limit)

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
            lambda cursor, limit, rid=region.id: client.wells.list(rid, cursor=cursor, limit=limit),
            "wells",
        )
        print(f"    {len(wells)} wells")
        projects = collect_all(
            lambda cursor, limit, rid=region.id: client.projects.list(
                rid, cursor=cursor, limit=limit
            ),
            "projects",
        )
        print(f"    {len(projects)} projects")


if __name__ == "__main__":
    main()

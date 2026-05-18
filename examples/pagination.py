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


def collect_all_regions(client: WhitsonPVTClientV2) -> list:
    all_regions = []
    page = client.regions.list()

    while True:
        all_regions.extend(page.regions)
        if not page.pagination.next_cursor:
            break
        page = client.regions.list()

    return all_regions


def collect_all(client, list_method, collection_attr: str) -> list:
    all_items = []
    page = list_method()

    while True:
        all_items.extend(getattr(page, collection_attr))
        if not page.pagination.next_cursor:
            break
        page = list_method()

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
        projects = collect_all(
            client,
            lambda rid=region.id: client.projects.list(rid),
            "projects",
        )
        print(f"    {len(projects)} projects")


if __name__ == "__main__":
    main()

"""Walk all pages of v2 paginated endpoints.

Demonstrates:
- Using iterate() for lazy cursor-based pagination
- Using list_all() for eager collection across pages
- Fetching all regions, wells, and projects across pages
"""

import os

from dotenv import load_dotenv

from whitson_pvt_sdk import WhitsonPVTClient


def print_region_summary(client: WhitsonPVTClient, limit: int = 100) -> None:
    """Stream regions lazily, fetching one page at a time."""
    print("First regions:")
    for index, region in enumerate(client.regions.iterate(limit=limit), start=1):
        print(f"  - {region.name} (id={region.id})")
        if index == 5:
            break


def print_region_inventory(client: WhitsonPVTClient, limit: int = 100) -> None:
    """Collect regions eagerly, then collect related wells/projects per region."""
    regions = client.regions.list_all(limit=limit)
    print(f"Collected {len(regions)} regions total")

    for region in regions[:5]:
        wells = client.wells.list_all(region_id=region.id, limit=limit)
        projects = client.projects.list_all(region_id=region.id, limit=limit)
        print(f"  - {region.name} (id={region.id})")
        print(f"    {len(wells)} wells")
        print(f"    {len(projects)} projects")


def main() -> None:
    load_dotenv()

    client = WhitsonPVTClient(
        base_url=os.environ.get("WHITSON_BASE_URL", "https://internal.pvt.whitson.com"),
    )

    print_region_summary(client)
    print_region_inventory(client)


if __name__ == "__main__":
    main()

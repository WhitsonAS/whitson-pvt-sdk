"""Basic connect and list example.

Demonstrates:
- Loading credentials from environment variables
- Creating a WhitsonPVTClient
- Listing regions
- Iterating v2 pagination
"""

import os

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.models.manual import ClientCredentials


def main() -> None:
    client_id = os.environ["WHITSON_CLIENT_ID"]
    client_secret = os.environ["WHITSON_CLIENT_SECRET"]
    base_url = os.environ.get("WHITSON_BASE_URL", "https://internal.pvt.whitson.com")

    client = WhitsonPVTClient(
        credentials=ClientCredentials(
            client_id=client_id,
            client_secret=client_secret,
        ),
        base_url=base_url,
    )

    page = client.regions.list()
    print(f"Regions (page 1): {len(page.regions)}")

    for region in page.regions:
        print(f"  - {region.name} (id={region.id})")

    while page.pagination.next_cursor:
        page = client.regions.list()
        print(f"Regions (next page): {len(page.regions)}")
        for region in page.regions:
            print(f"  - {region.name} (id={region.id})")


if __name__ == "__main__":
    main()

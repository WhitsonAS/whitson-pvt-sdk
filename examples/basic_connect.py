"""Basic connect and list example.

Demonstrates:
- Reading the API token from the PVT_TOKEN environment variable
- Creating a WhitsonPVTClient
- Listing regions
- Iterating v2 pagination with the lazy iterate() helper
"""

import os

from dotenv import load_dotenv

from whitson_pvt_sdk import WhitsonPVTClient


def main() -> None:
    load_dotenv()

    client = WhitsonPVTClient(
        base_url=os.environ.get("WHITSON_BASE_URL", "https://internal.pvt.whitson.com"),
    )

    print("Regions:")
    for region in client.regions.iterate(limit=50):
        print(f"  - {region.name} (id={region.id})")


if __name__ == "__main__":
    main()

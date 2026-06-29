"""Basic connect and list example.

Demonstrates:
- Loading credentials from environment variables
- Creating a WhitsonPVTClient
- Listing regions
- Iterating v2 pagination with the lazy iterate() helper
"""

import os

from dotenv import load_dotenv

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.shared.models import ClientCredentials


def main() -> None:
    load_dotenv()

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

    print("Regions:")
    for region in client.regions.iterate(limit=50):
        print(f"  - {region.name} (id={region.id})")


if __name__ == "__main__":
    main()

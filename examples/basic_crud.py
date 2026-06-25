"""Create, read, and update a region.

Demonstrates:
- Using generated Pydantic models for requests
- Creating a region with required fields
- Reading a region back
- Updating a region with exclude_unset semantics
"""

import os

from dotenv import load_dotenv

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.shared.models import ClientCredentials
from whitson_pvt_sdk.v2.models import CreateRegionModel, UpdateRegionModel


def main() -> None:
    load_dotenv()

    client = WhitsonPVTClient(
        credentials=ClientCredentials(
            client_id=os.environ["WHITSON_CLIENT_ID"],
            client_secret=os.environ["WHITSON_CLIENT_SECRET"],
        ),
        base_url=os.environ.get("WHITSON_BASE_URL", "https://internal.pvt.whitson.com"),
    )

    created = client.regions.create(
        CreateRegionModel(
            name="Example Region",
            region_type="asset",
            reservoir_type="Conventional",
        )
    )

    print(f"Created region: {created.name} (id={created.id})")

    fetched = client.regions.get(region_id=created.id)
    print(f"Fetched region: {fetched.name}")

    updated = client.regions.update(
        region_id=created.id,
        data=UpdateRegionModel(name="Renamed Example Region"),
    )
    print(f"Updated region: {updated.name}")


if __name__ == "__main__":
    main()

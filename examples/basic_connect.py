"""Basic connect and list example.

Demonstrates:
- Loading credentials from environment variables
- Creating a WhitsonPVTClient
- Listing regions
- Iterating v2 pagination
- Running a v2 flash calculation
"""

import os

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.shared.models import ClientCredentials
from whitson_pvt_sdk.v2.models import (
    CalculationCompositionEntryModel,
    FlashCalculationInputModel,
    FlashCalculationRequestModel,
)


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

    page = client.regions.list(limit=50)
    print(f"Regions (page 1): {len(page.regions)}")

    for region in page.regions:
        print(f"  - {region.name} (id={region.id})")

    while page.pagination.next_cursor:
        page = client.regions.list(cursor=page.pagination.next_cursor, limit=50)
        print(f"Regions (next page): {len(page.regions)}")
        for region in page.regions:
            print(f"  - {region.name} (id={region.id})")

    # NOTE: Replace this with a valid fluid model id from your whitson PVT account.
    fluid_model_id = 123
    flash = client.calculations.calculate_flash(
        FlashCalculationRequestModel(
            fluid_model_id=fluid_model_id,
            pressure_unit="bara",
            temperature_unit="C",
            inputs=[
                FlashCalculationInputModel(
                    pressure=200.0,
                    temperature=80.0,
                    feed_composition=[
                        CalculationCompositionEntryModel(
                            component_name="C1",
                            molar_amount=0.9,
                        ),
                        CalculationCompositionEntryModel(
                            component_name="C2",
                            molar_amount=0.1,
                        ),
                    ],
                )
            ],
        )
    )
    first_result = flash.results[0]
    if first_result.status == "success":
        print(f"Flash phases: {first_result.result.number_of_phases}")
    else:
        print(f"Flash calculation failed: {first_result.error.message}")


if __name__ == "__main__":
    main()

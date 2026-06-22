"""Run a v2 flash calculation.

Demonstrates:
- Creating a WhitsonPVTClient
- Building calculation request models
- Running a flash calculation
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
    client = WhitsonPVTClient(
        credentials=ClientCredentials(
            client_id=os.environ["WHITSON_CLIENT_ID"],
            client_secret=os.environ["WHITSON_CLIENT_SECRET"],
        ),
        base_url=os.environ.get("WHITSON_BASE_URL", "https://internal.pvt.whitson.com"),
    )

    # Replace this with a valid fluid model id from your whitson PVT account.
    fluid_model_id = int(os.environ.get("WHITSON_FLUID_MODEL_ID", "123"))
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

"""Run a v2 flash calculation.

Demonstrates:
- Creating a WhitsonPVTClient
- Fetching a sample feed composition
- Running a flash calculation
"""

import os

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.shared.models import ClientCredentials
from whitson_pvt_sdk.v2.models import (
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

    fluid_model_id = 123
    sample_id = 456

    feed_composition = client.calculations.get_sample_feed_composition(
        fluid_model_id=fluid_model_id,
        sample_id=sample_id,
        source="slate_to_slate_converted",
    )
    # For multiple samples, use the dict returned by sample id:
    # feed_compositions = client.calculations.get_sample_feed_compositions(
    #     fluid_model_id=fluid_model_id,
    #     sample_ids=[456, 789],
    #     source="slate_to_slate_converted",
    # )
    # feed_composition = feed_compositions[456]

    flash = client.calculations.calculate_flash(
        FlashCalculationRequestModel(
            fluid_model_id=fluid_model_id,
            pressure_unit="bara",
            temperature_unit="C",
            inputs=[
                FlashCalculationInputModel(
                    pressure=50.0,
                    temperature=50.0,
                    feed_composition=feed_composition,
                )
                # Multiple inputs can be provided for multiple flash calculations. For example:
                # FlashCalculationInputModel(
                #     pressure=50.0,
                #     temperature=50.0,
                #     feed_composition=feed_composition[789],
                # )
            ],
        )
    )
    print(flash.model_dump_json())


if __name__ == "__main__":
    main()

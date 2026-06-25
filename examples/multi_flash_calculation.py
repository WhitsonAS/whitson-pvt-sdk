"""Run multi sample flash calculation.

Demonstrates:
- Creating a WhitsonPVTClient
- Fetching feed composition for multiple samples
- Running a flash calculation
"""

import os

from dotenv import load_dotenv

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.shared.models import ClientCredentials
from whitson_pvt_sdk.utils import write_json
from whitson_pvt_sdk.v2.models import (
    FlashCalculationInputModel,
    FlashCalculationRequestModel,
)


def main() -> None:
    load_dotenv()

    client = WhitsonPVTClient(
        credentials=ClientCredentials(
            client_id=os.environ["WHITSON_CLIENT_ID"],
            client_secret=os.environ["WHITSON_CLIENT_SECRET"],
        ),
        base_url=os.environ.get("WHITSON_BASE_URL", "https://internal.pvt.whitson.com"),
    )

    fluid_model_id = 123
    sample_ids = [456, 789]

    feed_compositions = client.calculations.get_sample_feed_compositions(
        fluid_model_id=fluid_model_id,
        sample_ids=sample_ids,
        source="slate_to_slate_converted",
    )

    flash = client.calculations.calculate_flash(
        FlashCalculationRequestModel(
            fluid_model_id=fluid_model_id,
            pressure_unit="bara",
            temperature_unit="C",
            inputs=[
                FlashCalculationInputModel(
                    pressure=50.0,
                    temperature=50.0,
                    feed_composition=feed_compositions[456],
                ),
                FlashCalculationInputModel(
                    pressure=50.0,
                    temperature=50.0,
                    feed_composition=feed_compositions[789],
                ),
            ],
        )
    )
    write_json(flash, "multi_flash_results.json")


if __name__ == "__main__":
    main()

"""Run a v2 saturation pressure calculation.

Demonstrates:
- Creating a WhitsonPVTClient
- Fetching a sample feed composition
- Running a saturation pressure calculation
"""

import os

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.shared.models import ClientCredentials
from whitson_pvt_sdk.utils import print_json
from whitson_pvt_sdk.v2.models import (
    SaturationPressureCalculationInputModel,
    SaturationPressureCalculationRequestModel,
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

    saturation_pressure = client.calculations.calculate_saturation_pressure(
        SaturationPressureCalculationRequestModel(
            fluid_model_id=fluid_model_id,
            temperature_unit="C",
            inputs=[
                SaturationPressureCalculationInputModel(
                    temperature=50.0,
                    feed_composition=feed_composition,
                )
                # Multiple inputs can be provided for multiple saturation pressure calculations:
                # SaturationPressureCalculationInputModel(
                #     temperature=50.0,
                #     feed_composition=feed_composition[789],
                # )
            ],
        )
    )

    print_json(saturation_pressure)
    # from whitson_pvt_sdk.utils import write_json
    # write_json(saturation_pressure, "saturation_pressure_response.json")


if __name__ == "__main__":
    main()

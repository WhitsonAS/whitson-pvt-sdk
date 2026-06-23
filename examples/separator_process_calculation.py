"""Run a v2 separator process calculation.

Demonstrates:
- Creating a WhitsonPVTClient
- Fetching a sample feed composition
- Running a separator process calculation
"""

import os

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.shared.models import ClientCredentials
from whitson_pvt_sdk.utils import print_json
from whitson_pvt_sdk.v2.models import (
    SeparatorProcessCalculationInputModel,
    SeparatorProcessCalculationRequestModel,
    SurfaceProcessModel,
    SurfaceProcessStageModel,
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

    separator_process = client.calculations.calculate_separator_process(
        SeparatorProcessCalculationRequestModel(
            fluid_model_id=fluid_model_id,
            surface_process=SurfaceProcessModel(
                pressure_unit="bara",
                temperature_unit="C",
                stages=[SurfaceProcessStageModel(pressure=50.0, temperature=50.0)],
            ),
            inputs=[
                SeparatorProcessCalculationInputModel(feed_composition=feed_composition)
                # Multiple inputs can be provided for multiple separator process calculations:
                # SeparatorProcessCalculationInputModel(feed_composition=feed_composition[789])
            ],
        )
    )

    print_json(separator_process)
    # from whitson_pvt_sdk.utils import write_json
    # write_json(separator_process, "separator_process_response.json")


if __name__ == "__main__":
    main()

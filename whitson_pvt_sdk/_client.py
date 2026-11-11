from whitson_pvt_sdk.auth import resolve_credential
from whitson_pvt_sdk.http import HTTPTransport
from whitson_pvt_sdk.shared.models import RetryConfig
from whitson_pvt_sdk.v2 import resources


class WhitsonPVTClient:
    """Client for the whitson PVT external API.

    The bearer token is the ``token=`` argument, or the ``PVT_TOKEN`` environment
    variable when ``token`` is omitted.

    Usage::

        from whitson_pvt_sdk import WhitsonPVTClient

        client = WhitsonPVTClient(base_url="https://internal.pvt.whitson.com")
        regions = client.regions.list()
        well = client.wells.get(well_id=123)
    """

    def __init__(
        self,
        *,
        base_url: str,
        token: str | None = None,
        retry_config: RetryConfig = RetryConfig(),
        timeout: float = 30.0,
        file_timeout: float = 60.0,
    ) -> None:
        transport = HTTPTransport(
            resolve_credential(token),
            base_url,
            retry_config=retry_config,
            timeout=timeout,
            file_timeout=file_timeout,
        )
        self._transport = transport
        self.regions = resources.Regions(transport)
        self.wells = resources.Wells(transport)
        self.samples = resources.Samples(transport)
        self.projects = resources.Projects(transport)
        self.fluid_models = resources.FluidModels(transport)
        self.black_oil_tables = resources.BlackOilTables(transport)
        self.reports = resources.Reports(transport)
        self.calculations = resources.Calculations(transport)
        self.import_records = resources.ImportRecords(transport)
        self.import_sessions = resources.ImportSessions(transport)

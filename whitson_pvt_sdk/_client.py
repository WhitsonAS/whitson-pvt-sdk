from whitson_pvt_sdk.auth import resolve_base_url, resolve_credential
from whitson_pvt_sdk.http import HTTPTransport
from whitson_pvt_sdk.shared.models import RetryConfig
from whitson_pvt_sdk.v2 import resources


class WhitsonPVTClient:
    """Client for the whitson PVT external API.

    The deployment is ``base_url``, else the ``WHITSON_PVT_URL`` environment variable, else
    the default login stored by ``wpvt auth login``. The credential is the ``token=``
    argument, else the ``WHITSON_PVT_TOKEN`` environment variable, else the stored login for
    that deployment, which renews itself and is never sent to another deployment.

    Usage::

        from whitson_pvt_sdk import WhitsonPVTClient

        with WhitsonPVTClient(base_url="https://internal.pvt.whitson.com") as client:
            regions = client.regions.list()
            well = client.wells.get(well_id=123)

    ``close()`` releases the connections; the ``with`` block calls it on exit.
    Calling it again is harmless, and a request after it raises ``RuntimeError``.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        retry_config: RetryConfig = RetryConfig(),
        timeout: float = 30.0,
        file_timeout: float = 60.0,
    ) -> None:
        url = resolve_base_url(base_url)
        transport = HTTPTransport(
            resolve_credential(url, token).credential,
            url,
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
        self.me = resources.Me(transport)

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> "WhitsonPVTClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

from importlib import metadata

from .http import HTTPTransport
from .shared.models import ClientCredentials, RetryConfig
from .v2 import WhitsonPVTClientV2

try:
    __version__ = metadata.version("whitson-pvt-sdk")
except metadata.PackageNotFoundError:  # pragma: no cover - source tree without package metadata
    __version__ = "0.0.0+unknown"


def WhitsonPVTClient(
    *,
    credentials: ClientCredentials,
    base_url: str,
    version: str = "v2",
    retry_config: RetryConfig | None = None,
    timeout: float = 30.0,
    file_timeout: float = 60.0,
) -> WhitsonPVTClientV2:
    """Create a whitson PVT SDK client for the external API v2.

    Usage::

        from whitson_pvt_sdk import WhitsonPVTClient
        from whitson_pvt_sdk.shared.models import ClientCredentials

        client = WhitsonPVTClient(
            credentials=ClientCredentials(client_id="...", client_secret="..."),
            base_url="https://internal.pvt.whitson.com",
        )
        regions = client.regions.list()
        well = client.wells.get(well_id=123)
    """
    match version:
        case "v2":
            pass
        case "v1":
            raise ValueError(
                "External API v1 was removed in whitson-pvt-sdk 1.4.0. Use version='v2' "
                "(the default), or pin whitson-pvt-sdk<1.4: 1.3.x still supports v1."
            )
        case _:
            raise ValueError(f"Unknown version: {version!r}. Supported versions: ['v2']")

    return WhitsonPVTClientV2(
        HTTPTransport(
            credentials,
            base_url,
            retry_config=retry_config,
            timeout=timeout,
            file_timeout=file_timeout,
        )
    )


__all__ = ["WhitsonPVTClient", "__version__"]

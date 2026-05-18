import warnings
from typing import Literal, overload

from .http import HTTPTransport
from .v1 import WhitsonPVTV1Client
from .v2 import WhitsonPVTV2Client

__version__ = "0.1.0"

_DEPRECATED: dict[str, str] = {"v1": "v2"}
"""Map of deprecated versions to their replacements.
Example: _DEPRECATED = {"v1": "v2"} — v1 still works but warns.
"""

_SUPPORTED = frozenset({"v1", "v2"})


@overload
def WhitsonPVTClient(
    *,
    credentials,
    base_url: str,
    version: Literal["v2"] = "v2",
    auth0_domain: str | None = None,
    audience: str | None = None,
) -> WhitsonPVTV2Client: ...


@overload
def WhitsonPVTClient(
    *,
    credentials,
    base_url: str,
    version: Literal["v1"],
    auth0_domain: str | None = None,
    audience: str | None = None,
) -> WhitsonPVTV1Client: ...


@overload
def WhitsonPVTClient(
    *,
    credentials,
    base_url: str,
    version: str,
    auth0_domain: str | None = None,
    audience: str | None = None,
) -> WhitsonPVTV1Client | WhitsonPVTV2Client: ...


def WhitsonPVTClient(
    *,
    credentials,
    base_url: str,
    version: str = "v2",
    auth0_domain: str | None = None,
    audience: str | None = None,
) -> WhitsonPVTV1Client | WhitsonPVTV2Client:
    """Create a whitson PVT SDK client for the selected external API version.

    Usage::

        from whitson_pvt_sdk import WhitsonPVTClient
        from whitson_pvt_sdk.models.manual import ClientCredentials

        client = WhitsonPVTClient(
            credentials=ClientCredentials(client_id="...", client_secret="..."),
            base_url="https://internal.pvt.whitson.com",
        )
        regions = client.regions.list()
        well = client.wells.get(well_id=123)
    """
    transport = HTTPTransport(
        credentials,
        base_url,
        version=version,
        auth0_domain=auth0_domain,
        audience=audience,
    )

    if version in _DEPRECATED:
        warnings.warn(
            f"Version {version!r} is deprecated. Use {_DEPRECATED[version]!r} instead.",
            DeprecationWarning,
            stacklevel=2,
        )

    match version:
        case "v1":
            return WhitsonPVTV1Client(transport)
        case "v2":
            return WhitsonPVTV2Client(transport)
        case _:
            if version in _SUPPORTED:
                raise RuntimeError(
                    f"Version {version} is supported but not yet wired. "
                    "This is a bug — please report it."
                )
            raise ValueError(
                f"Unknown version: {version!r}. Supported versions: {sorted(_SUPPORTED)}"
            )


__all__ = ["WhitsonPVTClient"]

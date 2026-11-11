from importlib import metadata

from ._client import WhitsonPVTClient

try:
    __version__ = metadata.version("whitson-pvt-sdk")
except metadata.PackageNotFoundError:  # pragma: no cover - source tree without package metadata
    __version__ = "0.0.0+unknown"


__all__ = ["WhitsonPVTClient", "__version__"]

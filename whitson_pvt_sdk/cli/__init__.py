import sys
from enum import IntEnum

INSTALL_HINT = (
    "The wpvt command needs the cli extra. Install it with:\n"
    '  pip install "whitson-pvt-sdk[cli]"\n'
    'or: uv tool install "whitson-pvt-sdk[cli]"'
)


class ExitCode(IntEnum):
    OK = 0
    ERROR = 1
    USAGE = 2
    AUTHENTICATION = 3
    SERVER = 4
    REFUSED = 5


def main() -> None:
    try:
        from whitson_pvt_sdk.cli._app import app
    except ModuleNotFoundError as exc:
        if exc.name != "typer":
            raise
        print(INSTALL_HINT, file=sys.stderr)  # noqa: T201 - runs without Typer, so before cli._output can load
        raise SystemExit(ExitCode.USAGE) from None
    app()

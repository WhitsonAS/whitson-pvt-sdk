import json
from pathlib import Path

from pydantic import BaseModel


def to_json(data: object, *, indent: int = 2) -> str:
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json")
    return json.dumps(data, indent=indent, default=str)


def print_json(data: object, *, indent: int = 2) -> None:
    print(to_json(data, indent=indent))  # noqa: T201 - printing is this public helper's purpose


def write_json(
    data: object,
    path: str | Path = "output.json",
    *,
    indent: int = 2,
    overwrite: bool = False,
) -> Path:
    requested_path = Path(path)
    output_path = requested_path if overwrite else _available_output_path(requested_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(to_json(data, indent=indent) + "\n")
    return output_path


def _available_output_path(path: Path) -> Path:
    if not path.exists():
        return path

    index = 1
    while True:
        candidate = path.parent / f"{path.stem}_{index}{path.suffix}"
        if not candidate.exists():
            return candidate
        index += 1

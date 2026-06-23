import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def to_json(data: object, *, indent: int = 2) -> str:
    return json.dumps(_to_jsonable(data), indent=indent, default=str)


def print_json(data: object, *, indent: int = 2) -> None:
    print(to_json(data, indent=indent))


def write_json(
    data: object,
    path: str | Path | None = None,
    *,
    indent: int = 2,
    overwrite: bool = False,
) -> Path:
    requested_path = Path("output.json") if path is None else Path(path)
    output_path = requested_path if overwrite else _available_output_path(requested_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(to_json(data, indent=indent) + "\n")
    return output_path


def _to_jsonable(data: object) -> Any:
    if isinstance(data, BaseModel):
        return data.model_dump(mode="json")
    return data


def _available_output_path(path: Path) -> Path:
    if not path.exists():
        return path

    index = 1
    while True:
        candidate = path.parent / f"{path.stem}_{index}{path.suffix}"
        if not candidate.exists():
            return candidate
        index += 1

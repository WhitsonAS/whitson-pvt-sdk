import re
from typing import Any

from sdk_generator.config import RESOURCE_ORDER


def to_snake(value: str) -> str:
    value = value.replace("-", "_").replace(" ", "_")
    value = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[^0-9a-zA-Z_]+", "_", value)
    return re.sub(r"_+", "_", value).strip("_").lower()


def to_pascal(value: str) -> str:
    return "".join(part.capitalize() for part in value.split("_"))


def singular(value: str) -> str:
    if value.endswith("ies"):
        return f"{value[:-3]}y"
    if value.endswith("s"):
        return value[:-1]
    return value


def sort_resources(resources: dict[str, Any]) -> list[str]:
    order = {resource: index for index, resource in enumerate(RESOURCE_ORDER)}
    return sorted(resources, key=lambda resource: (order.get(resource, len(order)), resource))

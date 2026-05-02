"""Tool contract used by the Core Runtime."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


class RiskTier(StrEnum):
    READ_ONLY = "read_only"
    WRITE = "write"
    HIGH = "high"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    risk_tier: RiskTier = RiskTier.READ_ONLY
    read_only: bool = True


@dataclass(frozen=True)
class ToolObservation:
    ok: bool
    content: str
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "content": self.content, "metadata": self.metadata or {}}


class Tool(Protocol):
    spec: ToolSpec

    def execute(self, arguments: dict[str, Any]) -> ToolObservation:
        """Run the tool with validated arguments."""


class FunctionTool:
    """Small adapter for simple Python callables."""

    def __init__(self, spec: ToolSpec, fn: Callable[[dict[str, Any]], ToolObservation]) -> None:
        self.spec = spec
        self._fn = fn

    def execute(self, arguments: dict[str, Any]) -> ToolObservation:
        return self._fn(arguments)


def validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> None:
    """Validate a conservative subset of JSON Schema used by starter tools."""

    if schema.get("type") != "object":
        raise ValueError("Tool parameter schema must be an object schema.")
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    missing = required - set(arguments)
    if missing:
        raise ValueError(f"Missing required tool arguments: {sorted(missing)}")
    unexpected = set(arguments) - set(properties)
    if schema.get("additionalProperties") is False and unexpected:
        raise ValueError(f"Unexpected tool arguments: {sorted(unexpected)}")
    for name, value in arguments.items():
        prop = properties.get(name, {})
        expected = prop.get("type")
        if expected == "string" and not isinstance(value, str):
            raise ValueError(f"Tool argument '{name}' must be a string.")
        if expected == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"Tool argument '{name}' must be an integer.")
        if expected == "number":
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueError(f"Tool argument '{name}' must be a number.")
        if expected == "boolean" and not isinstance(value, bool):
            raise ValueError(f"Tool argument '{name}' must be a boolean.")
        if expected == "array":
            if not isinstance(value, list):
                raise ValueError(f"Tool argument '{name}' must be an array.")
            min_items = prop.get("minItems")
            if isinstance(min_items, int) and len(value) < min_items:
                raise ValueError(
                    f"Tool argument '{name}' must contain at least {min_items} elements."
                )
            items_schema = prop.get("items", {})
            item_type = items_schema.get("type")
            for i, item in enumerate(value):
                if item_type == "string" and not isinstance(item, str):
                    raise ValueError(f"Tool argument '{name}[{i}]' must be a string.")

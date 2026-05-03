"""@agent.tool decorator for the Decorator-Driven API."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from enum import StrEnum
from typing import Any, Literal, get_args, get_origin, get_type_hints

from pydantic import BaseModel

from naqsha.tools.context import AgentContext


class RiskTier(StrEnum):
    """Tool risk classification for Tool Policy enforcement."""

    READ_ONLY = "read_only"
    WRITE = "write"
    HIGH = "high"


class ToolDefinitionError(Exception):
    """Raised at decoration time when a tool function signature is malformed."""


def _is_optional(type_hint: Any) -> tuple[bool, Any]:
    """Check if a type hint is Optional[T] and return (is_optional, inner_type)."""
    origin = get_origin(type_hint)
    if origin is not type(None) and origin is not Literal:  # noqa: E721
        args = get_args(type_hint)
        if type(None) in args:
            # This is Optional[T] which is Union[T, None]
            non_none_args = [arg for arg in args if arg is not type(None)]
            if len(non_none_args) == 1:
                return True, non_none_args[0]
    return False, type_hint


def _type_to_json_schema(type_hint: Any, param_name: str) -> dict[str, Any]:
    """
    Convert a Python type hint to a JSON Schema Draft 2020-12 definition.

    Supports:
    - Primitive types: str, int, float, bool
    - Optional[T]
    - list[T] (as array)
    - dict[str, T] (as object with additionalProperties)
    - Pydantic BaseModel subclasses
    """
    is_optional, inner_type = _is_optional(type_hint)

    # Handle the inner type
    origin = get_origin(inner_type)

    # Primitive types
    if inner_type is str:
        schema = {"type": "string"}
    elif inner_type is int:
        schema = {"type": "integer"}
    elif inner_type is float:
        schema = {"type": "number"}
    elif inner_type is bool:
        schema = {"type": "boolean"}
    # List[T]
    elif origin is list:
        args = get_args(inner_type)
        if not args:
            raise ToolDefinitionError(
                f"Parameter '{param_name}': list type hint must specify "
                "element type (e.g., list[str])"
            )
        item_schema = _type_to_json_schema(args[0], f"{param_name}[]")
        schema = {"type": "array", "items": item_schema}
    # Dict[str, T]
    elif origin is dict:
        args = get_args(inner_type)
        if not args or len(args) != 2:
            raise ToolDefinitionError(
                f"Parameter '{param_name}': dict type hint must be dict[str, T]"
            )
        if args[0] is not str:
            raise ToolDefinitionError(
                f"Parameter '{param_name}': dict keys must be str, got {args[0]}"
            )
        value_schema = _type_to_json_schema(args[1], f"{param_name}[value]")
        schema = {"type": "object", "additionalProperties": value_schema}
    # Pydantic BaseModel
    elif inspect.isclass(inner_type) and issubclass(inner_type, BaseModel):
        # Use Pydantic's built-in schema generation
        schema = inner_type.model_json_schema()
    else:
        raise ToolDefinitionError(
            f"Parameter '{param_name}': unsupported type hint {inner_type}. "
            "Supported types: str, int, float, bool, Optional[T], list[T], "
            "dict[str, T], Pydantic BaseModel"
        )

    return schema


def _generate_schema(func: Callable[..., Any], description: str | None) -> dict[str, Any]:
    """
    Generate a JSON Schema Draft 2020-12 definition from a function signature.

    The schema is stored on the function as `__tool_schema__` and includes:
    - Function name
    - Description (from decorator or docstring)
    - Parameters schema (excluding `ctx: AgentContext`)
    """
    sig = inspect.signature(func)

    # Get type hints (resolves forward references)
    try:
        type_hints = get_type_hints(func)
    except Exception as exc:
        raise ToolDefinitionError(
            f"Failed to resolve type hints for {func.__name__}: {exc}"
        ) from exc

    # Extract description
    if description is None:
        description = (func.__doc__ or "").strip().split("\n")[0] or func.__name__

    # Build parameter schema
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        # Skip AgentContext injection parameter
        if param_name in type_hints and type_hints[param_name] is AgentContext:
            continue

        # Require type hints for all non-ctx parameters
        if param_name not in type_hints:
            raise ToolDefinitionError(
                f"Parameter '{param_name}' in {func.__name__} must have a type hint"
            )

        type_hint = type_hints[param_name]

        # Generate schema for this parameter
        param_schema = _type_to_json_schema(type_hint, param_name)
        properties[param_name] = param_schema

        # Check if required (no default value and not Optional)
        is_optional, _ = _is_optional(type_hint)
        if param.default is inspect.Parameter.empty and not is_optional:
            required.append(param_name)

    # Build the complete schema
    schema = {
        "name": func.__name__,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }

    return schema


def tool(
    *,
    risk_tier: RiskTier = RiskTier.READ_ONLY,
    description: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for defining tools using the Decorator-Driven API.

    Usage:
        @agent.tool(risk_tier=RiskTier.WRITE, description="Write a file")
        def write_file(path: str, content: str, ctx: AgentContext) -> str:
            '''Write content to a file.'''
            # Implementation
            return "File written"

    The decorator:
    1. Generates a JSON Schema from the function's type hints and docstring
    2. Stores the schema on the function as `__tool_schema__`
    3. Marks the function as a tool with `__is_naqsha_tool__ = True`
    4. Stores the risk tier as `__tool_risk_tier__`
    5. Stores whether the tool is read-only as `__tool_read_only__`

    Parameters with type hint `AgentContext` are automatically injected at runtime
    and omitted from the public schema.

    Args:
        risk_tier: Tool risk classification (READ_ONLY, WRITE, HIGH)
        description: Optional description (defaults to first line of docstring)

    Raises:
        ToolDefinitionError: If the function signature is malformed
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if not callable(func):
            raise ToolDefinitionError(f"{func} is not callable")

        try:
            schema = _generate_schema(func, description)
        except ToolDefinitionError:
            raise
        except Exception as exc:
            raise ToolDefinitionError(
                f"Failed to generate schema for {func.__name__}: {exc}"
            ) from exc

        func.__tool_schema__ = schema  # type: ignore[attr-defined]
        func.__is_naqsha_tool__ = True  # type: ignore[attr-defined]
        func.__tool_risk_tier__ = risk_tier  # type: ignore[attr-defined]
        func.__tool_read_only__ = risk_tier == RiskTier.READ_ONLY  # type: ignore[attr-defined]

        return func

    return decorator


# Convenience namespace for @agent.tool syntax
class agent:
    """Namespace for the @agent.tool decorator."""

    tool = staticmethod(tool)

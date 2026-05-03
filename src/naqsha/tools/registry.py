"""ToolRegistry: holds decorated tools and exports schemas."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from naqsha.tools.decorator import RiskTier


class ToolRegistry:
    """
    Registry for tools decorated with @agent.tool.
    
    The registry:
    - Holds references to decorated tool functions
    - Supports lookup by name
    - Exports schema lists for Model Adapters
    - Validates that registered functions are properly decorated
    """

    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}

    def register(self, func: Callable[..., Any]) -> None:
        """
        Register a tool function.
        
        Args:
            func: A function decorated with @agent.tool
        
        Raises:
            ValueError: If the function is not decorated or name conflicts
        """
        if not hasattr(func, "__is_naqsha_tool__"):
            raise ValueError(
                f"Function {func.__name__} must be decorated with @agent.tool"
            )
        
        if not hasattr(func, "__tool_schema__"):
            raise ValueError(
                f"Function {func.__name__} is missing __tool_schema__ attribute"
            )
        
        schema = func.__tool_schema__
        name = schema["name"]
        
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered")
        
        self._tools[name] = func

    def get(self, name: str) -> Callable[..., Any] | None:
        """
        Look up a tool by name.
        
        Args:
            name: Tool name
        
        Returns:
            The tool function, or None if not found
        """
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def names(self) -> frozenset[str]:
        """Return the set of registered tool names."""
        return frozenset(self._tools.keys())

    def export_schemas(self) -> list[dict[str, Any]]:
        """
        Export tool schemas for Model Adapters.
        
        Returns a list of schema dictionaries suitable for inclusion in
        model API requests. Each schema includes name, description, and
        parameters.
        
        Returns:
            List of tool schemas
        """
        schemas = []
        for func in self._tools.values():
            schema = func.__tool_schema__.copy()
            schemas.append(schema)
        return schemas

    def get_risk_tier(self, name: str) -> RiskTier | None:
        """
        Get the risk tier for a tool.
        
        Args:
            name: Tool name
        
        Returns:
            The tool's risk tier, or None if not found
        """
        func = self._tools.get(name)
        if func is None:
            return None
        return func.__tool_risk_tier__

    def is_read_only(self, name: str) -> bool:
        """
        Check if a tool is read-only.
        
        Args:
            name: Tool name
        
        Returns:
            True if the tool is read-only, False otherwise
        """
        func = self._tools.get(name)
        if func is None:
            return False
        return func.__tool_read_only__

    def clear(self) -> None:
        """Clear all registered tools (primarily for testing)."""
        self._tools.clear()

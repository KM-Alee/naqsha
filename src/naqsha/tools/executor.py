"""ToolExecutor: resolves AgentContext injection and executes tools."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, get_type_hints

from naqsha.tools.base import ToolObservation
from naqsha.tools.context import AgentContext


def tool_error_observation(exc: Exception) -> ToolObservation:
    """Normalize a caught tool exception into a structured failed observation."""

    return ToolObservation(
        ok=False,
        content=str(exc),
        metadata={"error": type(exc).__name__, "tool_error": True},
    )


class ToolExecutor:
    """
    Executes decorated tools with automatic AgentContext injection.

    The executor inspects signatures, injects ``AgentContext`` when requested via
    type hints, handles sync and async tool functions, and wraps exceptions as
    failed ``ToolObservation`` values so the runtime can enforce circuit breaker
    policy without crashing the agent loop.
    """

    def __init__(self, context: AgentContext) -> None:
        self._context = context

    def execute(
        self,
        func: Callable[..., Any],
        arguments: dict[str, Any],
    ) -> ToolObservation:
        """
        Execute a tool function with automatic context injection.

        For async tools, returns a coroutine that must be awaited.
        """

        sig = inspect.signature(func)
        try:
            type_hints = get_type_hints(func)
        except Exception:
            type_hints = {}
        needs_context = False
        for param_name, param in sig.parameters.items():
            ann = type_hints.get(param_name, param.annotation)
            if ann is AgentContext:
                needs_context = True
                break

        call_kwargs = arguments.copy()
        if needs_context:
            call_kwargs["ctx"] = self._context

        try:
            if inspect.iscoroutinefunction(func):
                return self._execute_async(func, call_kwargs)
            result = func(**call_kwargs)
        except Exception as exc:
            return tool_error_observation(exc)

        return self._convert_result(result)

    async def _execute_async(
        self,
        func: Callable[..., Any],
        call_kwargs: dict[str, Any],
    ) -> ToolObservation:
        """Execute an async tool and convert the result."""
        try:
            result = await func(**call_kwargs)
        except Exception as exc:
            return tool_error_observation(exc)

        return self._convert_result(result)

    def _convert_result(self, result: Any) -> ToolObservation:
        """Convert a tool result to ToolObservation."""
        if isinstance(result, ToolObservation):
            return result
        if isinstance(result, str):
            return ToolObservation(ok=True, content=result)
        if isinstance(result, dict):
            return ToolObservation(
                ok=result.get("ok", True),
                content=result.get("content", ""),
                metadata=result.get("metadata"),
            )
        return ToolObservation(ok=True, content=str(result))

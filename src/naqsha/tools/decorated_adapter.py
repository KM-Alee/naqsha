"""Bridge ``@agent.tool`` callables to the legacy ``Tool`` / ``FunctionTool`` protocol."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any, cast

from naqsha.tools.base import FunctionTool, RiskTier, ToolObservation, ToolSpec
from naqsha.tools.context import AgentContext
from naqsha.tools.executor import ToolExecutor


def _coerce_policy_risk_tier(dec_tier: object) -> RiskTier:
    if isinstance(dec_tier, RiskTier):
        return dec_tier
    if isinstance(dec_tier, str):
        return RiskTier(dec_tier)
    return RiskTier(dec_tier.value)


def decorated_to_function_tool(
    func: Callable[..., Any],
    get_context: Callable[[], AgentContext],
) -> FunctionTool:
    """Wrap a decorated tool function as a ``FunctionTool`` with runtime context injection."""
    schema = func.__tool_schema__
    dec_tier = func.__tool_risk_tier__
    tier = _coerce_policy_risk_tier(dec_tier)
    spec = ToolSpec(
        name=schema["name"],
        description=schema["description"],
        parameters=schema["parameters"],
        risk_tier=tier,
        read_only=tier == RiskTier.READ_ONLY,
    )

    def execute(arguments: dict[str, Any]) -> ToolObservation:
        executor = ToolExecutor(get_context())
        result = executor.execute(func, arguments)
        if inspect.iscoroutine(result):
            return asyncio.run(result)
        return cast("ToolObservation", result)

    return FunctionTool(spec, execute)

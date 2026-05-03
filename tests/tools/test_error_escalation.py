"""Structured tool error escalation: executor wraps and scheduler normalizes."""

from __future__ import annotations

from pathlib import Path

import pytest

from naqsha.budgets import BudgetLimits, BudgetMeter
from naqsha.protocols.nap import ToolCall
from naqsha.scheduler import ToolScheduler
from naqsha.tools import AgentContext, ToolExecutor, agent
from naqsha.tools.base import FunctionTool, ToolObservation, ToolSpec


@pytest.mark.asyncio
async def test_async_tool_exception_becomes_observation() -> None:
    ctx = AgentContext(
        shared_memory=None,
        private_memory=None,
        span=None,
        workspace_path=Path("."),
        agent_id="x",
        run_id="y",
    )
    executor = ToolExecutor(ctx)

    @agent.tool()
    async def bad() -> str:
        raise OverflowError("wide")

    out = await executor.execute(bad, {})
    assert not out.ok
    assert out.metadata["error"] == "OverflowError"
    assert out.metadata.get("tool_error") is True


def test_scheduler_catches_raises_with_normalized_metadata() -> None:
    def explode(arguments: dict[str, object]) -> ToolObservation:
        raise ValueError("scheduler path")

    t = FunctionTool(
        ToolSpec(
            name="x",
            description="",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        explode,
    )
    sch = ToolScheduler()
    outs = sch.execute(
        (ToolCall(id="1", name="x", arguments={}),),
        {"x": t},
        meter=BudgetMeter(BudgetLimits()),
    )
    assert len(outs) == 1
    obs = outs[0].observation
    assert not obs.ok
    assert obs.metadata["error"] == "ValueError"
    assert obs.metadata.get("tool_error") is True


def test_decorated_executor_and_scheduler_compatible_fingerprints(
    tmp_path: Path,
) -> None:
    """Same exception maps to identical ``error`` metadata from both paths."""

    @agent.tool()
    def flaky() -> str:
        raise ValueError("z")

    from naqsha.tools.decorated_adapter import decorated_to_function_tool

    def get_ctx() -> AgentContext:
        return AgentContext(
            shared_memory=None,
            private_memory=None,
            span=None,
            workspace_path=tmp_path,
            agent_id="a",
            run_id="r",
        )

    deco_tool = decorated_to_function_tool(flaky, get_ctx)
    sch = ToolScheduler()
    scheduler_out = sch.execute(
        (ToolCall(id="s", name=deco_tool.spec.name, arguments={}),),
        {deco_tool.spec.name: deco_tool},
        meter=BudgetMeter(BudgetLimits()),
    )
    ex = ToolExecutor(get_ctx())
    executor_out = ex.execute(flaky, {})

    a = scheduler_out[0].observation
    assert executor_out.metadata and a.metadata
    assert executor_out.metadata.get("error") == a.metadata.get("error")

"""Tool-Based Delegation: orchestrator tools that run a worker ``CoreRuntime``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from naqsha.core.event_bus import RuntimeEventBus
from naqsha.core.runtime import CoreRuntime
from naqsha.memory.engine import DynamicMemoryEngine
from naqsha.orchestration.topology import AgentRoleConfig, TeamTopology
from naqsha.tools.base import FunctionTool, RiskTier, ToolObservation, ToolSpec
from naqsha.tracing.span import SpanContext


def build_delegate_tool(
    worker: AgentRoleConfig,
    topology: TeamTopology,
    workspace_path: Path,
    memory_engine: DynamicMemoryEngine,
    parent_runtime_slot: list[CoreRuntime | None],
    event_bus: RuntimeEventBus | None,
) -> FunctionTool:
    tool_name = topology.delegate_tool_name_for_worker(worker.agent_id)

    def execute(arguments: dict[str, Any]) -> ToolObservation:
        return _run_delegation(
            arguments,
            worker=worker,
            topology=topology,
            workspace_path=workspace_path,
            memory_engine=memory_engine,
            parent_runtime_slot=parent_runtime_slot,
            event_bus=event_bus,
            tool_name=tool_name,
        )

    spec = ToolSpec(
        name=tool_name,
        description=(
            f"Delegate a task to worker agent {worker.agent_id!r}. "
            "Runs that agent's loop to completion and returns its final answer."
        ),
        parameters={
            "type": "object",
            "properties": {"task": {"type": "string", "description": "Task instructions."}},
            "required": ["task"],
            "additionalProperties": False,
        },
        risk_tier=RiskTier.WRITE,
        read_only=False,
    )
    return FunctionTool(spec, execute)


def _run_delegation(
    arguments: dict[str, Any],
    *,
    worker: AgentRoleConfig,
    topology: TeamTopology,
    workspace_path: Path,
    memory_engine: DynamicMemoryEngine,
    parent_runtime_slot: list[CoreRuntime | None],
    event_bus: RuntimeEventBus | None,
    tool_name: str,
) -> ToolObservation:
    task = arguments.get("task")
    if not isinstance(task, str) or not task.strip():
        return ToolObservation(ok=False, content="Argument 'task' must be a non-empty string.")

    parent = parent_runtime_slot[0]
    if parent is None:
        return ToolObservation(ok=False, content="Orchestrator runtime is not initialized.")

    run_id = parent._current_run_id  # noqa: SLF001
    if not run_id:
        return ToolObservation(ok=False, content="No active orchestrator run_id for delegation.")

    parent_ctx: SpanContext = parent._active_span_context  # noqa: SLF001
    child_ctx = parent_ctx.child_span(worker.agent_id)

    from naqsha.orchestration.team_runtime import build_worker_runtime

    try:
        child_rt = build_worker_runtime(
            worker,
            topology=topology,
            workspace_path=workspace_path,
            memory_engine=memory_engine,
            span_context=child_ctx,
            event_bus=event_bus if event_bus is not None else parent.config.event_bus,
            approval_gate=parent.config.approval_gate,
        )
        result = child_rt.run(task.strip(), run_id=run_id)
    except Exception as exc:  # noqa: BLE001
        return ToolObservation(
            ok=False,
            content=f"Delegation to {worker.agent_id!r} failed: {exc}",
            metadata={
                "kind": "TaskFailedError",
                "worker_agent_id": worker.agent_id,
                "error": type(exc).__name__,
                "tool": tool_name,
            },
        )

    if result.failed:
        meta: dict[str, Any] = {
            "kind": "TaskFailedError",
            "worker_agent_id": worker.agent_id,
            "failure_code": result.failure_code,
        }
        if result.failure_code == "circuit_breaker_tripped":
            meta["circuit_breaker"] = True
        return ToolObservation(
            ok=False,
            content=(
                f"Worker {worker.agent_id!r} task failed: "
                f"{result.failure_code or 'worker_run_failed'}"
            ),
            metadata=meta,
        )
    return ToolObservation(ok=True, content=result.answer or "")

"""Construct ``CoreRuntime`` for Team Workspace orchestrator and workers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from naqsha.core.approvals import ApprovalGate, InteractiveApprovalGate, StaticApprovalGate
from naqsha.core.event_bus import RuntimeEventBus
from naqsha.core.policy import ToolPolicy
from naqsha.core.runtime import CoreRuntime, RuntimeConfig
from naqsha.memory.engine import DynamicMemoryEngine
from naqsha.memory.sharing import open_team_memory_engine
from naqsha.models.factory import model_client_from_profile
from naqsha.orchestration.delegation import build_delegate_tool
from naqsha.orchestration.topology import (
    MEMORY_DECORATED_TOOL_NAMES,
    AgentRoleConfig,
    TeamTopology,
    WorkspaceSection,
    parse_team_topology_file,
)
from naqsha.profiles import ProfileValidationError, RunProfile, parse_run_profile
from naqsha.tools.base import Tool
from naqsha.tools.context import AgentContext
from naqsha.tools.decorated_adapter import decorated_to_function_tool
from naqsha.tools.memory_schema import list_memory_tables, memory_schema
from naqsha.tools.starter import starter_tools
from naqsha.tracing.jsonl import JsonlTraceStore
from naqsha.tracing.sanitizer import ObservationSanitizer
from naqsha.tracing.span import SpanContext


def run_profile_for_topology_agent(
    agent: AgentRoleConfig,
    *,
    workspace: WorkspaceSection,
    trace_dir: Path,
    tool_root: Path,
    base_dir: Path,
) -> RunProfile:
    tiers = agent.approval_required_tiers or workspace.approval_required_tiers
    data: dict[str, Any] = {
        "name": agent.agent_id,
        "model": agent.model_adapter,
        "trace_dir": str(trace_dir),
        "tool_root": str(tool_root),
        "memory_adapter": "none",
        "memory_token_budget": 512,
        "auto_approve": workspace.auto_approve,
        "sanitizer_max_chars": workspace.sanitizer_max_chars,
        "approval_required_tiers": sorted(t.value for t in tiers),
        "budgets": {
            "max_steps": agent.budgets.max_steps,
            "max_tool_calls": agent.budgets.max_tool_calls,
            "wall_clock_seconds": agent.budgets.wall_clock_seconds,
            "per_tool_seconds": agent.budgets.per_tool_seconds,
            "max_model_tokens": agent.budgets.max_model_tokens,
        },
    }
    if agent.fake_model_messages is not None:
        data["fake_model"] = {"messages": list(agent.fake_model_messages)}
    i = agent.instructions.strip()
    if i:
        data["instructions"] = i
    if agent.openai_compat is not None:
        data["openai_compat"] = agent.openai_compat
    if agent.anthropic is not None:
        data["anthropic"] = agent.anthropic
    if agent.gemini is not None:
        data["gemini"] = agent.gemini
    if agent.ollama is not None:
        data["ollama"] = agent.ollama

    names = sorted(agent.tools)
    delegate_prefix = "delegate_to_"

    parse_names = sorted(
        n
        for n in names
        if not n.startswith(delegate_prefix) and n not in MEMORY_DECORATED_TOOL_NAMES
    )
    if parse_names:
        data["allowed_tools"] = parse_names
    profile = parse_run_profile(data, base_dir=base_dir)
    if profile.allowed_tool_names != frozenset(agent.tools):
        profile = replace(profile, allowed_tool_names=frozenset(agent.tools))
    return profile


def tool_policy_for_topology_agent(
    agent: AgentRoleConfig,
    tools: dict[str, Tool],
    *,
    workspace: WorkspaceSection,
) -> ToolPolicy:
    allowed = agent.tools
    missing = allowed - frozenset(tools)
    if missing:
        raise ProfileValidationError(
            f"Agent {agent.agent_id!r} is missing tool implementations: {sorted(missing)}."
        )
    tiers = agent.approval_required_tiers or workspace.approval_required_tiers
    return ToolPolicy(allowed_tools=allowed, approval_required_tiers=tiers)


def build_tools_for_agent(
    agent: AgentRoleConfig,
    workspace_path: Path,
    memory_engine: DynamicMemoryEngine | None,
    get_runtime: Callable[[], CoreRuntime | None],
) -> dict[str, Tool]:
    """Assemble tool dict for an agent (starter tools, memory tools, excluding delegation)."""

    root = workspace_path.resolve()
    starters = starter_tools(root)
    out: dict[str, Tool] = {}
    for name in agent.tools:
        if name.startswith("delegate_to_"):
            continue
        if name in starters:
            out[name] = starters[name]

    dec_map = {"memory_schema": memory_schema, "list_memory_tables": list_memory_tables}
    for name, fn in dec_map.items():
        if name not in agent.tools:
            continue
        if memory_engine is None:
            raise ProfileValidationError(
                f"Agent {agent.agent_id!r} lists {name!r} but team memory engine is missing."
            )

        def make_ctx_factory(
            getter: Callable[[], CoreRuntime | None],
        ) -> Callable[[], AgentContext]:
            def ctx_factory() -> AgentContext:
                rt = getter()
                if rt is None:
                    raise RuntimeError("CoreRuntime not initialized for tool context.")
                return rt._make_agent_context()

            return ctx_factory

        out[name] = decorated_to_function_tool(fn, make_ctx_factory(get_runtime))

    return out


def build_orchestrator_tools(
    topology: TeamTopology,
    workspace_path: Path,
    memory_engine: DynamicMemoryEngine,
    parent_runtime_slot: list[CoreRuntime | None],
    event_bus: RuntimeEventBus | None,
) -> dict[str, Tool]:
    orch = topology.agents[topology.orchestrator_id]
    tools = build_tools_for_agent(
        orch,
        workspace_path,
        memory_engine,
        lambda: parent_runtime_slot[0],
    )
    for worker in topology.worker_agents().values():
        dt = build_delegate_tool(
            worker,
            topology,
            workspace_path,
            memory_engine,
            parent_runtime_slot,
            event_bus,
        )
        tools[dt.spec.name] = dt
    return tools


def build_worker_runtime(
    worker: AgentRoleConfig,
    *,
    topology: TeamTopology,
    workspace_path: Path,
    memory_engine: DynamicMemoryEngine,
    span_context: SpanContext,
    event_bus: RuntimeEventBus | None,
    approval_gate: ApprovalGate,
) -> CoreRuntime:
    child_slot: list[CoreRuntime | None] = [None]
    tools = build_tools_for_agent(
        worker,
        workspace_path,
        memory_engine,
        lambda: child_slot[0],
    )
    trace_dir = topology.workspace.resolve_trace_dir(workspace_path)
    profile = run_profile_for_topology_agent(
        worker,
        workspace=topology.workspace,
        trace_dir=trace_dir,
        tool_root=workspace_path,
        base_dir=workspace_path,
    )
    policy = tool_policy_for_topology_agent(
        worker,
        tools,
        workspace=topology.workspace,
    )
    config = RuntimeConfig(
        model=model_client_from_profile(profile),
        tools=tools,
        trace_store=JsonlTraceStore(trace_dir),
        policy=policy,
        budgets=worker.budgets,
        approval_gate=approval_gate,
        sanitizer=ObservationSanitizer(max_chars=topology.workspace.sanitizer_max_chars),
        memory=None,
        memory_token_budget=512,
        shared_memory_scope=memory_engine.get_shared_scope(),
        private_memory_scope=memory_engine.get_private_scope(worker.agent_id),
        workspace_path=workspace_path.resolve(),
        agent_id=worker.agent_id,
        trace_id=span_context.trace_id,
        span_context=span_context,
        event_bus=event_bus,
        max_retries=worker.max_retries,
        agent_instructions=profile.instructions,
    )
    rt = CoreRuntime(config)
    child_slot[0] = rt
    return rt


def build_team_orchestrator_runtime(
    topology: TeamTopology,
    workspace_path: Path,
    *,
    event_bus: RuntimeEventBus | None = None,
    approve_prompt: bool = False,
    implicit_tool_approval: bool = False,
) -> CoreRuntime:
    """Create the orchestrator ``CoreRuntime`` for a parsed ``TeamTopology``."""

    workspace_path = workspace_path.resolve()
    engine = open_team_memory_engine(workspace_path, topology.memory)
    parent_slot: list[CoreRuntime | None] = [None]
    tools = build_orchestrator_tools(
        topology,
        workspace_path,
        engine,
        parent_slot,
        event_bus,
    )
    orch = topology.agents[topology.orchestrator_id]
    trace_dir = topology.workspace.resolve_trace_dir(workspace_path)
    profile = run_profile_for_topology_agent(
        orch,
        workspace=topology.workspace,
        trace_dir=trace_dir,
        tool_root=workspace_path,
        base_dir=workspace_path,
    )
    policy = tool_policy_for_topology_agent(
        orch,
        tools,
        workspace=topology.workspace,
    )
    gate: ApprovalGate
    if topology.workspace.auto_approve:
        gate = StaticApprovalGate(approved=True)
    elif implicit_tool_approval:
        gate = StaticApprovalGate(approved=True)
    elif approve_prompt:
        gate = InteractiveApprovalGate()
    else:
        gate = StaticApprovalGate(approved=False)
    config = RuntimeConfig(
        model=model_client_from_profile(profile),
        tools=tools,
        trace_store=JsonlTraceStore(trace_dir),
        policy=policy,
        budgets=orch.budgets,
        approval_gate=gate,
        sanitizer=ObservationSanitizer(max_chars=topology.workspace.sanitizer_max_chars),
        memory=None,
        memory_token_budget=512,
        shared_memory_scope=engine.get_shared_scope(),
        private_memory_scope=engine.get_private_scope(orch.agent_id),
        workspace_path=workspace_path,
        agent_id=orch.agent_id,
        trace_id=None,
        span_context=None,
        event_bus=event_bus,
        max_retries=orch.max_retries,
        agent_instructions=profile.instructions,
    )
    rt = CoreRuntime(config)
    parent_slot[0] = rt
    return rt


def build_team_workspace_runtime(
    project_root: Path,
    *,
    event_bus: RuntimeEventBus | None = None,
    approve_prompt: bool = False,
    implicit_tool_approval: bool = False,
) -> CoreRuntime:
    """Parse ``project_root/naqsha.toml`` and return the orchestrator ``CoreRuntime``.

    ``implicit_tool_approval=True`` is for GUIs (e.g. Command Center) with no tty for
    :class:`InteractiveApprovalGate`, where the operator already chose interactive execution.
    """

    topo = parse_team_topology_file(project_root / "naqsha.toml")
    return build_team_orchestrator_runtime(
        topo,
        project_root.expanduser().resolve(),
        event_bus=event_bus,
        approve_prompt=approve_prompt,
        implicit_tool_approval=implicit_tool_approval,
    )

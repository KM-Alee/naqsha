"""Profile-to-runtime wiring (library surface; not CLI-specific)."""

from __future__ import annotations

from typing import Any

from naqsha.approvals import ApprovalGate, InteractiveApprovalGate, StaticApprovalGate
from naqsha.core.event_bus import RuntimeEventBus
from naqsha.memory.inmemory import InMemoryMemoryPort
from naqsha.memory.simplemem_cross import SimpleMemCrossMemoryPort
from naqsha.models.factory import model_client_from_profile
from naqsha.models.trace_replay import TraceReplayModelClient
from naqsha.policy import ToolPolicy
from naqsha.profiles import ProfileValidationError, RunProfile, describe_profile_dict
from naqsha.protocols.qaoa import TraceEvent
from naqsha.replay import nap_messages_from_trace, observations_by_call_id
from naqsha.runtime import CoreRuntime, RuntimeConfig
from naqsha.sanitizer import ObservationSanitizer
from naqsha.scheduler import ToolScheduler
from naqsha.tools.base import RiskTier, Tool
from naqsha.tools.starter import starter_tools
from naqsha.trace.jsonl import JsonlTraceStore


def tool_policy_for_profile(profile: RunProfile, tools: dict[str, Tool]) -> ToolPolicy:
    if profile.allowed_tool_names is None:
        allowed = frozenset(tools)
    else:
        allowed = profile.allowed_tool_names
        missing = allowed - frozenset(tools)
        if missing:
            raise ProfileValidationError(
                f"allowed_tools contains names not loaded from Starter Tool Set: "
                f"{sorted(missing)}."
            )
    return ToolPolicy(
        allowed_tools=allowed,
        approval_required_tiers=profile.approval_required_tiers,
    )


def build_runtime(
    profile: RunProfile,
    *,
    approve_prompt: bool = False,
    event_bus: RuntimeEventBus | None = None,
) -> CoreRuntime:
    tools = starter_tools(profile.tool_root)
    policy = tool_policy_for_profile(profile, tools)

    model = model_client_from_profile(profile)

    memory = None
    if profile.memory_adapter == "inmemory":
        memory = InMemoryMemoryPort()
    elif profile.memory_adapter == "simplemem_cross":
        memory = SimpleMemCrossMemoryPort(
            project=profile.memory_cross_project,
            database_path=profile.memory_cross_database,
        )

    if profile.auto_approve:
        gate: ApprovalGate = StaticApprovalGate(approved=True)
    elif approve_prompt:
        gate = InteractiveApprovalGate()
    else:
        gate = StaticApprovalGate(approved=False)

    return CoreRuntime(
        RuntimeConfig(
            model=model,
            tools=tools,
            trace_store=JsonlTraceStore(profile.trace_dir),
            policy=policy,
            budgets=profile.budgets,
            approval_gate=gate,
            sanitizer=ObservationSanitizer(max_chars=profile.sanitizer_max_chars),
            memory=memory,
            memory_token_budget=profile.memory_token_budget,
            event_bus=event_bus,
            agent_instructions=profile.instructions,
        )
    )


def build_trace_replay_runtime(
    profile: RunProfile,
    reference_events: list[TraceEvent],
    *,
    approve_prompt: bool = False,
    event_bus: RuntimeEventBus | None = None,
) -> CoreRuntime:
    """Same wiring as ``build_runtime`` with trace-scripted model and recorded tools."""

    tools = starter_tools(profile.tool_root)
    policy = tool_policy_for_profile(profile, tools)

    memory = None
    if profile.memory_adapter == "inmemory":
        memory = InMemoryMemoryPort()
    elif profile.memory_adapter == "simplemem_cross":
        memory = SimpleMemCrossMemoryPort(
            project=profile.memory_cross_project,
            database_path=profile.memory_cross_database,
        )

    if profile.auto_approve:
        gate: ApprovalGate = StaticApprovalGate(approved=True)
    elif approve_prompt:
        gate = InteractiveApprovalGate()
    else:
        gate = StaticApprovalGate(approved=False)

    messages = nap_messages_from_trace(reference_events)
    recorded = observations_by_call_id(reference_events)

    return CoreRuntime(
        RuntimeConfig(
            model=TraceReplayModelClient(messages),
            tools=tools,
            trace_store=JsonlTraceStore(profile.trace_dir),
            policy=policy,
            budgets=profile.budgets,
            approval_gate=gate,
            sanitizer=ObservationSanitizer(max_chars=profile.sanitizer_max_chars),
            scheduler=ToolScheduler(recorded_observations=recorded),
            memory=memory,
            memory_token_budget=profile.memory_token_budget,
            event_bus=event_bus,
            agent_instructions=profile.instructions,
        )
    )


def inspect_policy_payload(profile: RunProfile) -> dict[str, Any]:
    tools_obj = starter_tools(profile.tool_root)
    policy = tool_policy_for_profile(profile, tools_obj)

    tools_meta: list[dict[str, Any]] = []
    for name in sorted(policy.allowed_tools):
        tool = tools_obj[name]
        needs = tool.spec.risk_tier in policy.approval_required_tiers
        tools_meta.append(
            {
                "name": name,
                "risk_tier": tool.spec.risk_tier.value,
                "tier_triggers_policy_approval": needs,
                "effective_with_static_gate": (
                    "allow"
                    if not needs or profile.auto_approve
                    else "denied_without_approval"
                ),
            }
        )

    unknown_starter = frozenset(tools_obj) - policy.allowed_tools
    return {
        "resolved_profile": describe_profile_dict(profile),
        "policy": {
            "allowed_tools": sorted(policy.allowed_tools),
            "approval_required_risk_tiers": sorted(t.value for t in policy.approval_required_tiers),
            "starter_tools_excluded_from_allowlist": sorted(unknown_starter),
            "approval_gate_mode": (
                "auto_approve_true" if profile.auto_approve else "auto_approve_false"
            ),
        },
        "tools": tools_meta,
        "risk_tiers_reference": sorted(t.value for t in RiskTier),
    }

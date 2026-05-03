"""Runtime-enforced Tool Policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from naqsha.approvals import ApprovalGate
from naqsha.protocols.nap import ToolCall
from naqsha.tools.base import RiskTier, Tool, validate_arguments


class PolicyDecisionKind(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


@dataclass(frozen=True)
class PolicyDecision:
    call_id: str
    tool_name: str
    decision: PolicyDecisionKind
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "decision": self.decision.value,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ToolPolicy:
    """Per-run tool allowlist and approval rules."""

    allowed_tools: frozenset[str]
    approval_required_tiers: frozenset[RiskTier] = frozenset({RiskTier.WRITE, RiskTier.HIGH})

    @classmethod
    def allow_all_starter_tools(cls, tools: dict[str, Tool]) -> ToolPolicy:
        return cls(allowed_tools=frozenset(tools))

    def decide(self, call: ToolCall, tools: dict[str, Tool]) -> PolicyDecision:
        tool = tools.get(call.name)
        if tool is None:
            return PolicyDecision(call.id, call.name, PolicyDecisionKind.DENY, "Unknown tool.")
        if call.name not in self.allowed_tools:
            return PolicyDecision(call.id, call.name, PolicyDecisionKind.DENY, "Tool not allowed.")
        try:
            validate_arguments(tool.spec.parameters, call.arguments)
        except ValueError as exc:
            return PolicyDecision(call.id, call.name, PolicyDecisionKind.DENY, str(exc))
        if tool.spec.risk_tier in self.approval_required_tiers:
            return PolicyDecision(
                call.id,
                call.name,
                PolicyDecisionKind.REQUIRE_APPROVAL,
                f"Tool risk tier '{tool.spec.risk_tier.value}' requires approval.",
            )
        return PolicyDecision(call.id, call.name, PolicyDecisionKind.ALLOW, "Tool allowed.")

    def enforce(
        self,
        call: ToolCall,
        tools: dict[str, Tool],
        approval_gate: ApprovalGate,
    ) -> PolicyDecision:
        decision = self.decide(call, tools)
        if decision.decision != PolicyDecisionKind.REQUIRE_APPROVAL:
            return decision

        tool = tools[call.name]
        if approval_gate.approve(call, tool.spec, decision.reason):
            return PolicyDecision(call.id, call.name, PolicyDecisionKind.ALLOW, "Approved.")
        return PolicyDecision(call.id, call.name, PolicyDecisionKind.DENY, "Approval denied.")

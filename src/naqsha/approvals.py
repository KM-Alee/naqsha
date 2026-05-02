"""Approval Gate interfaces."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Protocol

from naqsha.protocols.nap import ToolCall
from naqsha.tools.base import ToolSpec


class ApprovalGate(Protocol):
    """Blocking pre-execution checkpoint for high-risk side effects."""

    def approve(self, call: ToolCall, spec: ToolSpec, reason: str) -> bool:
        """Return whether a call may execute."""


@dataclass(frozen=True)
class StaticApprovalGate:
    """Deterministic approval gate for tests and local smoke runs."""

    approved: bool = False

    def approve(self, call: ToolCall, spec: ToolSpec, reason: str) -> bool:
        return self.approved


class InteractiveApprovalGate:
    """Prompt stdin once per required approval (CLI local use)."""

    def approve(self, call: ToolCall, spec: ToolSpec, reason: str) -> bool:
        sys.stderr.write(
            f"Approval required for tool {call.name!r} (risk tier {spec.risk_tier.value}).\n"
            f"Reason: {reason}\nApprove? [y/N]: "
        )
        sys.stderr.flush()
        line = sys.stdin.readline()
        return line.strip().lower() in {"y", "yes"}

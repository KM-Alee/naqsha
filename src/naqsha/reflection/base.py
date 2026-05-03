"""Reflection Loop contracts.

Reflection may propose isolated patches after evaluation, but this module must not
modify active runtime behavior or bypass human review.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from naqsha.protocols.qaoa import TraceEvent


@dataclass(frozen=True)
class ReflectionPatch:
    """Artifacts for human review.

    Merging into the active workspace is performed only by ``AutomatedRollbackManager``
    inside the reflection package when workspace policy allows auto-merge; there is no
    merge method on this object.
    """

    workspace: Path
    summary: str
    reliability_gate_passed: bool
    auto_merged: bool = False

    @property
    def ready_for_human_review(self) -> bool:
        """True when the Reliability Gate passed; merge still needs human approval."""

        return self.reliability_gate_passed


class ReflectionPatchEventSink(Protocol):
    """Callbacks for patch lifecycle (implemented by embedders using ``RuntimeEventBus``)."""

    def patch_merged(
        self,
        *,
        run_id: str,
        agent_id: str,
        patch_id: str,
        auto_merged: bool,
    ) -> None:
        """Patch merged into the team workspace after Reliability Gate pass."""

    def patch_rolled_back(
        self,
        *,
        run_id: str,
        agent_id: str,
        patch_id: str,
        reason: str,
    ) -> None:
        """Workspace restored after a failed post-merge boot check."""


class ReflectionLoop(Protocol):
    def propose_patch(self, trace: list[TraceEvent]) -> ReflectionPatch | None:
        """Create an isolated patch candidate, never a runtime hotpatch."""

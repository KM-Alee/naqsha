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
    workspace: Path
    summary: str
    reliability_gate_passed: bool


class ReflectionLoop(Protocol):
    def propose_patch(self, trace: list[TraceEvent]) -> ReflectionPatch | None:
        """Create an isolated patch candidate, never a runtime hotpatch."""

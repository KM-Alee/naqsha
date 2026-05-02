"""Memory Port contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from naqsha.tools.base import ToolObservation


@dataclass(frozen=True)
class MemoryRecord:
    content: str
    provenance: str


class MemoryPort(Protocol):
    """Durable memory boundary owned by the Core Runtime."""

    def start_run(self, run_id: str, query: str) -> None:
        """Start memory lifecycle for a run."""

    def retrieve(self, query: str, token_budget: int) -> list[MemoryRecord]:
        """Retrieve provenance-aware memory records."""

    def record_observation(self, run_id: str, tool: str, observation: ToolObservation) -> None:
        """Record sanitized tool observations."""

    def finish_run(self, run_id: str, answer: str | None) -> None:
        """Finalize memory lifecycle for a run."""

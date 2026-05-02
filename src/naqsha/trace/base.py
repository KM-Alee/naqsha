"""Trace Store port."""

from __future__ import annotations

from typing import Protocol

from naqsha.protocols.qaoa import TraceEvent


class TraceStore(Protocol):
    """Persistence boundary for QAOA Trace events."""

    def append(self, event: TraceEvent) -> None:
        """Persist one event."""

    def load(self, run_id: str) -> list[TraceEvent]:
        """Load events for a run."""

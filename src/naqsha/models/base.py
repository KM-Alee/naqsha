"""Model Client port."""

from __future__ import annotations

from typing import Protocol

from naqsha.memory.base import MemoryRecord
from naqsha.protocols.nap import NapMessage
from naqsha.protocols.qaoa import TraceEvent
from naqsha.tools.base import ToolSpec


class ModelClient(Protocol):
    """Return the next validated NAP message."""

    def next_message(
        self,
        *,
        query: str,
        trace: list[TraceEvent],
        tools: list[ToolSpec],
        memory: list[MemoryRecord],
    ) -> NapMessage:
        """Request the next model decision."""

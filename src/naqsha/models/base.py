"""Model Client port."""

from __future__ import annotations

from typing import Protocol

from naqsha.memory.base import MemoryRecord
from naqsha.models.nap import NapMessage
from naqsha.protocols.qaoa import TraceEvent
from naqsha.tools.base import ToolSpec
from naqsha.tracing.span import SpanContext


class ModelClient(Protocol):
    """Return the next validated NAP message."""

    def next_message(
        self,
        *,
        query: str,
        trace: list[TraceEvent],
        tools: list[ToolSpec],
        memory: list[MemoryRecord],
        span_context: SpanContext | None = None,
        instructions: str = "",
    ) -> NapMessage:
        """Request the next model decision.

        ``instructions`` is merged into the system prompt for adapters that rebuild
        the transcript from the trace (ignored by fake scripted / trace-replay paths).
        """

"""Model client that replays NAP messages scripted from a recorded QAOA Trace."""

from __future__ import annotations

from collections import deque

from naqsha.memory.base import MemoryRecord
from naqsha.models.base import ModelClient
from naqsha.protocols.nap import NapMessage
from naqsha.protocols.qaoa import TraceEvent
from naqsha.tools.base import ToolSpec


class TraceReplayExhausted(RuntimeError):
    """Raised when scripted trace replay needs another model message but the trace ends."""


class TraceReplayModelClient(ModelClient):
    """Emit the same NapAction / NapAnswer sequence stored in reference trace events."""

    def __init__(self, messages: list[NapMessage]) -> None:
        self._messages: deque[NapMessage] = deque(messages)

    def next_message(
        self,
        *,
        query: str,
        trace: list[TraceEvent],
        tools: list[ToolSpec],
        memory: list[MemoryRecord],
    ) -> NapMessage:
        del query, trace, tools, memory
        if not self._messages:
            raise TraceReplayExhausted(
                "Trace replay ran out of scripted model messages before the run finished."
            )
        return self._messages.popleft()

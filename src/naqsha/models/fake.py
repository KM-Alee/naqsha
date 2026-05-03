"""Deterministic fake Model Client for tests and local smoke runs."""

from __future__ import annotations

from collections import deque

from naqsha.memory.base import MemoryRecord
from naqsha.models.base import ModelClient
from naqsha.models.nap import NapAnswer, NapMessage, attach_span_context, parse_nap_message
from naqsha.protocols.qaoa import TraceEvent
from naqsha.tools.base import ToolSpec
from naqsha.tracing.span import SpanContext


class FakeModelClient(ModelClient):
    def __init__(self, messages: list[NapMessage | dict[str, object]] | None = None) -> None:
        parsed = []
        for message in messages or [NapAnswer(text="Fake model completed the run.")]:
            parsed.append(parse_nap_message(message) if isinstance(message, dict) else message)
        self.messages: deque[NapMessage] = deque(parsed)

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
        if self.messages:
            return attach_span_context(self.messages.popleft(), span_context)
        return attach_span_context(
            NapAnswer(text="Fake model has no more scripted messages."), span_context
        )

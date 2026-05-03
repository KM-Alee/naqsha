"""Span and SpanContext for Hierarchical QAOA Trace.

Spans enable OpenTelemetry-style tracing across multi-agent execution trees.
Every trace event in V2 carries span_id, parent_span_id, and agent_id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class SpanContext:
    """Immutable context carrying trace and span identifiers.
    
    SpanContext is propagated through the execution tree and attached to
    every trace event, enabling hierarchical trace reconstruction.
    """
    
    trace_id: str
    span_id: str
    parent_span_id: str | None
    agent_id: str
    
    def child_span(self, agent_id: str | None = None) -> SpanContext:
        """Create a child span context with this span as parent.
        
        Args:
            agent_id: Agent ID for the child span. If None, inherits from parent.
            
        Returns:
            New SpanContext with this span as parent.
        """
        return SpanContext(
            trace_id=self.trace_id,
            span_id=str(uuid4()),
            parent_span_id=self.span_id,
            agent_id=agent_id if agent_id is not None else self.agent_id,
        )


@dataclass
class Span:
    """Mutable span tracking execution metrics.
    
    A Span represents a unit of work in the execution tree. It accumulates
    metrics like token counts and latency as the work progresses.
    """
    
    context: SpanContext
    token_count: int = 0
    model_latency_ms: float | None = None
    tool_exec_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def add_tokens(self, count: int) -> None:
        """Add tokens to the span's total count."""
        self.token_count += count
    
    def set_model_latency(self, latency_ms: float) -> None:
        """Record model invocation latency."""
        self.model_latency_ms = latency_ms
    
    def set_tool_exec_time(self, exec_ms: float) -> None:
        """Record tool execution time."""
        self.tool_exec_ms = exec_ms
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize span to dictionary for trace events."""
        return {
            "trace_id": self.context.trace_id,
            "span_id": self.context.span_id,
            "parent_span_id": self.context.parent_span_id,
            "agent_id": self.context.agent_id,
            "token_count": self.token_count,
            "model_latency_ms": self.model_latency_ms,
            "tool_exec_ms": self.tool_exec_ms,
            "metadata": self.metadata,
        }


def create_root_span(trace_id: str, agent_id: str) -> Span:
    """Create a root span for a new trace.
    
    Args:
        trace_id: Unique identifier for the trace.
        agent_id: Identifier for the agent starting the trace.
        
    Returns:
        New Span with no parent.
    """
    context = SpanContext(
        trace_id=trace_id,
        span_id=str(uuid4()),
        parent_span_id=None,
        agent_id=agent_id,
    )
    return Span(context=context)

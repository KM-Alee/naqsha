"""
Typed Event Bus event models.

All events are Pydantic BaseModel subclasses that represent runtime state changes.
The Core Runtime emits these events; the TUI and other adapters subscribe to them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class RuntimeEvent(BaseModel):
    """Base class for all runtime events."""
    
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    

class RunStarted(RuntimeEvent):
    """Emitted when a run begins."""
    
    run_id: str
    agent_id: str
    query: str
    

class AgentActivated(RuntimeEvent):
    """Emitted when an agent becomes active in a run."""
    
    run_id: str
    agent_id: str
    

class StreamChunkReceived(RuntimeEvent):
    """Emitted when a streaming token chunk is received from the model."""
    
    run_id: str
    agent_id: str
    chunk: str


class BudgetProgress(RuntimeEvent):
    """Emitted after each agent step with current budget meter readings (Workbench TUI)."""

    run_id: str
    agent_id: str
    steps_used: int
    max_steps: int
    tool_calls_used: int
    max_tool_calls: int
    wall_clock_used_seconds: float
    wall_clock_limit_seconds: float
    

class ToolInvoked(RuntimeEvent):
    """Emitted when a tool is about to be invoked."""
    
    run_id: str
    agent_id: str
    tool_name: str
    call_id: str
    arguments: dict[str, Any]
    

class ToolCompleted(RuntimeEvent):
    """Emitted when a tool invocation completes successfully."""
    
    run_id: str
    agent_id: str
    tool_name: str
    call_id: str
    observation: str
    execution_time_ms: float | None = None
    

class ToolErrored(RuntimeEvent):
    """Emitted when a tool invocation fails."""
    
    run_id: str
    agent_id: str
    tool_name: str
    call_id: str
    error_message: str
    

class SpanOpened(RuntimeEvent):
    """Emitted when a new span is opened."""
    
    run_id: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    agent_id: str = ""
    

class SpanClosed(RuntimeEvent):
    """Emitted when a span is closed."""
    
    run_id: str
    trace_id: str
    span_id: str
    agent_id: str
    token_count: int | None = None
    model_latency_ms: float | None = None
    

class CircuitBreakerTripped(RuntimeEvent):
    """Emitted when a circuit breaker trips due to consecutive failures."""
    
    run_id: str
    agent_id: str
    tool_name: str
    consecutive_failures: int
    

class PatchMerged(RuntimeEvent):
    """Emitted when a Reflection Patch is merged."""
    
    run_id: str
    agent_id: str
    patch_id: str
    auto_merged: bool
    

class PatchRolledBack(RuntimeEvent):
    """Emitted when a Reflection Patch is rolled back."""
    
    run_id: str
    agent_id: str
    patch_id: str
    reason: str
    

class RunCompleted(RuntimeEvent):
    """Emitted when a run completes successfully."""
    
    run_id: str
    agent_id: str
    answer: str
    total_steps: int
    total_tokens: int | None = None
    

class RunFailed(RuntimeEvent):
    """Emitted when a run fails."""
    
    run_id: str
    agent_id: str
    error_message: str
    total_steps: int

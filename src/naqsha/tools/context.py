"""AgentContext: the stable public API for tool authors."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from naqsha.memory.base import MemoryPort
    from naqsha.memory.scope import MemoryScope
    from naqsha.tracing.span import Span


@dataclass(frozen=True)
class AgentContext:
    """
    Runtime context injected into tools that request it.
    
    This is the stable public API surface for tool authors. Tools can access
    runtime state by including a `ctx: AgentContext` parameter in their signature.
    The Core Runtime will automatically inject this context at execution time.
    
    Fields:
        shared_memory: Memory namespace accessible by all agents in a team (V2).
                      For V2 Dynamic Memory Engine, this is a MemoryScope.
                      For V1 compatibility, this may be a MemoryPort.
        private_memory: Memory namespace isolated to this specific agent (V2).
                       For V2 Dynamic Memory Engine, this is a MemoryScope.
                       For V1 compatibility, this may be a MemoryPort.
        span: Current trace span for attribution (V2).
        workspace_path: Absolute path to the Team Workspace root.
        agent_id: Unique identifier for the current agent.
        run_id: Unique identifier for the current run.
    """

    shared_memory: MemoryScope | MemoryPort | None
    private_memory: MemoryScope | MemoryPort | None
    span: Span | None
    workspace_path: Path
    agent_id: str
    run_id: str

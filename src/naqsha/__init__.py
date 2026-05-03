"""NAQSHA — flat public API for the V2 runtime.

Import stable types and helpers from this package (``from naqsha import …``) rather
than depending on internal submodule paths. Domain logic lives under
``naqsha.core``, ``naqsha.tools``, ``naqsha.memory``, and sibling packages; see the
developer documentation (MkDocs) for architecture and vocabulary.
"""

__version__ = "0.2.0"

# V2 Core Runtime and Event Bus
from naqsha.core.event_bus import RuntimeEventBus
from naqsha.core.events import (
    AgentActivated,
    BudgetProgress,
    CircuitBreakerTripped,
    PatchMerged,
    PatchRolledBack,
    RunCompleted,
    RunFailed,
    RunStarted,
    RuntimeEvent,
    SpanClosed,
    SpanOpened,
    StreamChunkReceived,
    ToolCompleted,
    ToolErrored,
    ToolInvoked,
)
from naqsha.core.runtime import CoreRuntime, RunResult, RuntimeConfig

# V2 Dynamic Memory Engine
from naqsha.memory import (
    DynamicMemoryEngine,
    ForbiddenDDLError,
    MemoryRetriever,
    MemoryScope,
    TeamMemoryConfig,
    open_team_memory_engine,
)

# V1 compatibility re-exports
from naqsha.orchestration import (
    TeamTopology,
    build_team_orchestrator_runtime,
    parse_team_topology,
    parse_team_topology_file,
)
from naqsha.profiles import RunProfile, load_run_profile

# V2 Decorator-Driven Tool API
from naqsha.tools import (
    AgentContext,
    RiskTier,
    ToolDefinitionError,
    ToolExecutor,
    ToolRegistry,
    agent,
    decorated_to_function_tool,
    tool,
)

# V2 Hierarchical QAOA Trace
from naqsha.tracing import Span, SpanContext, create_root_span
from naqsha.wiring import build_runtime, build_trace_replay_runtime, inspect_policy_payload
from naqsha.workbench import AgentWorkbench

__all__ = [
    # Core Runtime
    "CoreRuntime",
    "RunResult",
    "RuntimeConfig",
    # Event Bus
    "RuntimeEventBus",
    "RuntimeEvent",
    "RunStarted",
    "AgentActivated",
    "BudgetProgress",
    "StreamChunkReceived",
    "ToolInvoked",
    "ToolCompleted",
    "ToolErrored",
    "SpanOpened",
    "SpanClosed",
    "CircuitBreakerTripped",
    "PatchMerged",
    "PatchRolledBack",
    "RunCompleted",
    "RunFailed",
    # V2 Tool API
    "agent",
    "tool",
    "AgentContext",
    "RiskTier",
    "ToolDefinitionError",
    "ToolRegistry",
    "ToolExecutor",
    "decorated_to_function_tool",
    # V2 Hierarchical Trace
    "Span",
    "SpanContext",
    "create_root_span",
    # V2 Dynamic Memory Engine
    "DynamicMemoryEngine",
    "MemoryScope",
    "MemoryRetriever",
    "ForbiddenDDLError",
    "TeamMemoryConfig",
    "open_team_memory_engine",
    # Team Workspace orchestration
    "TeamTopology",
    "build_team_orchestrator_runtime",
    "parse_team_topology",
    "parse_team_topology_file",
    # V1 Compatibility
    "AgentWorkbench",
    "RunProfile",
    "build_runtime",
    "build_trace_replay_runtime",
    "inspect_policy_payload",
    "load_run_profile",
]

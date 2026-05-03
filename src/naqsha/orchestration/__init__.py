"""Team orchestration and Tool-Based Delegation."""

from __future__ import annotations

from naqsha.orchestration.delegation import build_delegate_tool
from naqsha.orchestration.team_runtime import (
    build_team_orchestrator_runtime,
    build_worker_runtime,
    run_profile_for_topology_agent,
)
from naqsha.orchestration.topology import (
    MEMORY_DECORATED_TOOL_NAMES,
    AgentRoleConfig,
    TeamTopology,
    WorkspaceSection,
    parse_team_topology,
    parse_team_topology_file,
)

__all__ = [
    "MEMORY_DECORATED_TOOL_NAMES",
    "AgentRoleConfig",
    "TeamTopology",
    "WorkspaceSection",
    "build_delegate_tool",
    "build_team_orchestrator_runtime",
    "build_worker_runtime",
    "parse_team_topology",
    "parse_team_topology_file",
    "run_profile_for_topology_agent",
]

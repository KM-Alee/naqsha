"""Reflection Loop boundaries."""

from naqsha.reflection.base import (
    ReflectionLoop,
    ReflectionPatch,
    ReflectionPatchEventSink,
)
from naqsha.reflection.candidate import build_candidate_markdown, build_meta_json
from naqsha.reflection.config import ReflectionTomlSettings, load_reflection_toml_settings
from naqsha.reflection.loop import (
    SimpleReflectionLoop,
    failing_gate_runner,
    noop_gate_runner,
)
from naqsha.reflection.reliability_gate import (
    RELIABILITY_GATE_TEST_PATHS,
    ReliabilityGateResult,
    resolve_project_root_for_gate,
    run_reliability_gate_subprocess,
)
from naqsha.reflection.rollback import AutomatedRollbackManager
from naqsha.reflection.workspace import (
    ReflectionWorkspaceError,
    assert_workspace_outside_package,
    create_isolated_workspace,
    naqsha_package_dir,
)

__all__ = [
    "RELIABILITY_GATE_TEST_PATHS",
    "AutomatedRollbackManager",
    "ReflectionLoop",
    "ReflectionPatch",
    "ReflectionPatchEventSink",
    "ReflectionTomlSettings",
    "ReflectionWorkspaceError",
    "ReliabilityGateResult",
    "SimpleReflectionLoop",
    "assert_workspace_outside_package",
    "build_candidate_markdown",
    "build_meta_json",
    "create_isolated_workspace",
    "failing_gate_runner",
    "load_reflection_toml_settings",
    "naqsha_package_dir",
    "noop_gate_runner",
    "resolve_project_root_for_gate",
    "run_reliability_gate_subprocess",
]

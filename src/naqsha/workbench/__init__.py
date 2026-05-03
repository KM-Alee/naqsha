"""High-level Agent Workbench API over Core Runtime and wiring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from naqsha.core.event_bus import RuntimeEventBus
from naqsha.core.events import PatchMerged, PatchRolledBack
from naqsha.eval_fixtures import (
    EvalFixture,
    build_fixture_from_trace,
    eval_check_result_dict,
    load_fixture,
    save_fixture,
    verify_trace_matches_fixture,
)
from naqsha.models.trace_replay import TraceReplayExhausted
from naqsha.profiles import RunProfile, load_run_profile
from naqsha.protocols.qaoa import TraceEvent
from naqsha.reflection.base import ReflectionPatch, ReflectionPatchEventSink
from naqsha.reflection.loop import SimpleReflectionLoop
from naqsha.reflection.rollback import AutomatedRollbackManager
from naqsha.replay import (
    TraceReplayError,
    compare_replay,
    first_query_from_trace,
    summarize_trace,
)
from naqsha.runtime import CoreRuntime, RunResult
from naqsha.scheduler import ReplayObservationMissing
from naqsha.trace.jsonl import JsonlTraceStore
from naqsha.trace_scan import latest_run_id, list_run_ids_by_recency
from naqsha.wiring import build_runtime, build_trace_replay_runtime, inspect_policy_payload


class RuntimeBusReflectionSink:
    """Maps reflection lifecycle callbacks to ``PatchMerged`` / ``PatchRolledBack`` bus events."""

    __slots__ = ("_bus", "_default_agent_id")

    def __init__(self, bus: RuntimeEventBus, *, default_agent_id: str = "") -> None:
        self._bus = bus
        self._default_agent_id = default_agent_id

    def patch_merged(
        self,
        *,
        run_id: str,
        agent_id: str,
        patch_id: str,
        auto_merged: bool,
    ) -> None:
        aid = agent_id or self._default_agent_id
        self._bus.emit(
            PatchMerged(run_id=run_id, agent_id=aid, patch_id=patch_id, auto_merged=auto_merged)
        )

    def patch_rolled_back(
        self,
        *,
        run_id: str,
        agent_id: str,
        patch_id: str,
        reason: str,
    ) -> None:
        aid = agent_id or self._default_agent_id
        self._bus.emit(
            PatchRolledBack(run_id=run_id, agent_id=aid, patch_id=patch_id, reason=reason)
        )


@dataclass
class WorkbenchPaths:
    """Resolved paths for an agent project."""

    cwd: Path
    trace_dir: Path


class AgentWorkbench:
    """Load profiles, run queries, summarize traces, eval, and reflection."""

    def __init__(self, profile: RunProfile) -> None:
        self._profile = profile

    @classmethod
    def from_profile_spec(cls, spec: str) -> AgentWorkbench:
        return cls(load_run_profile(spec))

    @property
    def profile(self) -> RunProfile:
        return self._profile

    def paths(self) -> WorkbenchPaths:
        return WorkbenchPaths(cwd=Path.cwd(), trace_dir=self._profile.trace_dir)

    def build_runtime(self, *, approve_prompt: bool = False) -> CoreRuntime:
        return build_runtime(self._profile, approve_prompt=approve_prompt)

    def run(
        self,
        query: str,
        *,
        approve_prompt: bool = False,
        rollback_manager: AutomatedRollbackManager | None = None,
        patch_event_sink: ReflectionPatchEventSink | None = None,
        event_bus: RuntimeEventBus | None = None,
    ) -> RunResult:
        mgr = rollback_manager or AutomatedRollbackManager()
        cwd = self.paths().cwd

        sink = patch_event_sink
        if sink is None and event_bus is not None:
            sink = RuntimeBusReflectionSink(event_bus)

        def _health() -> bool:
            try:
                rt = self.build_runtime(approve_prompt=approve_prompt)
                probe = rt.run("__naqsha_boot_probe__")
                return not probe.failed
            except Exception:
                return False

        mgr.verify_boot_if_pending(cwd, health_check=_health, event_sink=sink)
        return self.build_runtime(approve_prompt=approve_prompt).run(query)

    def policy_snapshot(self) -> dict[str, Any]:
        return inspect_policy_payload(self._profile)

    def trace_store(self) -> JsonlTraceStore:
        return JsonlTraceStore(self._profile.trace_dir)

    def summarize_run(self, run_id: str) -> Any:
        return summarize_trace(self.trace_store(), run_id)

    def list_runs(self) -> list[str]:
        return list_run_ids_by_recency(self._profile.trace_dir)

    def latest_run(self) -> str | None:
        return latest_run_id(self._profile.trace_dir)

    def replay_re_execute(
        self,
        reference_events: list[TraceEvent],
        *,
        approve_prompt: bool = False,
    ):
        """Re-run trace-scripted execution; returns (RunResult, ReplayDiff)."""

        query = first_query_from_trace(reference_events)
        runtime = build_trace_replay_runtime(
            self._profile,
            reference_events,
            approve_prompt=approve_prompt,
        )
        result = runtime.run(query)
        replay_events = self.trace_store().load(result.run_id)
        diff = compare_replay(reference_events, replay_events)
        return result, diff

    def save_eval_fixture(self, name: str, run_id: str, dest: Path) -> EvalFixture:
        events = self.trace_store().load(run_id)
        fix = build_fixture_from_trace(name=name, events=events)
        save_fixture(dest, fix)
        return fix

    def check_eval_fixture(
        self,
        run_id: str,
        fixture_path: Path,
        *,
        approve_prompt: bool = False,
    ) -> dict[str, Any]:
        fixture = load_fixture(fixture_path)
        reference = self.trace_store().load(run_id)
        trace_ok = len(verify_trace_matches_fixture(reference, fixture)) == 0
        try:
            result, diff = self.replay_re_execute(reference, approve_prompt=approve_prompt)
        except (TraceReplayError, TraceReplayExhausted, ReplayObservationMissing) as exc:
            return {
                "fixture_name": fixture.name,
                "passed": False,
                "error": str(exc),
            }
        replay_events = self.trace_store().load(result.run_id)
        return eval_check_result_dict(
            fixture=fixture,
            reference_events=reference,
            replay_events=replay_events,
            trace_ok=trace_ok,
        )

    def propose_improvement(
        self,
        run_id: str,
        *,
        workspace_parent: Path | None = None,
        event_bus: RuntimeEventBus | None = None,
    ) -> ReflectionPatch | None:
        events = self.trace_store().load(run_id)
        if not events:
            return None
        base = workspace_parent
        if base is None:
            base = Path.cwd() / ".naqsha" / "reflection-workspaces"
        sink = RuntimeBusReflectionSink(event_bus) if event_bus is not None else None
        loop = SimpleReflectionLoop(
            workspace_parent=base.expanduser().resolve(),
            team_workspace=self.paths().cwd,
            patch_event_sink=sink,
        )
        return loop.propose_patch(events)

"""High-level Agent Workbench API over Core Runtime and wiring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
from naqsha.reflection.base import ReflectionPatch
from naqsha.reflection.loop import SimpleReflectionLoop
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

    def run(self, query: str, *, approve_prompt: bool = False) -> RunResult:
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
    ) -> ReflectionPatch | None:
        events = self.trace_store().load(run_id)
        if not events:
            return None
        base = workspace_parent
        if base is None:
            base = Path.cwd() / ".naqsha" / "reflection-workspaces"
        loop = SimpleReflectionLoop(workspace_parent=base.expanduser().resolve())
        return loop.propose_patch(events)

"""Conservative Tool Scheduler."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass

from naqsha.budgets import BudgetMeter
from naqsha.protocols.nap import ToolCall
from naqsha.tools.base import Tool, ToolObservation


class ReplayObservationMissing(LookupError):
    """Raised when trace replay expected a recorded observation but none was stored."""


@dataclass(frozen=True)
class ScheduledObservation:
    call: ToolCall
    observation: ToolObservation


class ToolScheduler:
    """Execute approved calls serially unless all are safe read-only calls."""

    def __init__(self, recorded_observations: dict[str, ToolObservation] | None = None) -> None:
        """If set, approved tool calls return these observations by call id (no live tool I/O)."""

        self.recorded_observations = recorded_observations

    def can_parallelize(self, calls: tuple[ToolCall, ...], tools: dict[str, Tool]) -> bool:
        if len(calls) <= 1:
            return False
        names = [call.name for call in calls]
        return len(names) == len(set(names)) and all(
            tools[call.name].spec.read_only for call in calls
        )

    def execute(
        self,
        calls: tuple[ToolCall, ...],
        tools: dict[str, Tool],
        *,
        meter: BudgetMeter | None = None,
    ) -> list[ScheduledObservation]:
        if not calls:
            return []

        per_tool_timeout = meter.limits.per_tool_seconds if meter is not None else None

        def invoke(call: ToolCall) -> ToolObservation:
            if self.recorded_observations is not None:
                recorded = self.recorded_observations.get(call.id)
                if recorded is None:
                    raise ReplayObservationMissing(
                        f"No recorded observation for approved call id {call.id!r} "
                        f"(tool {call.name!r}). Is the trace complete?"
                    )
                return recorded
            try:
                return tools[call.name].execute(call.arguments)
            except Exception as exc:  # noqa: BLE001 - tool failures become observations.
                return ToolObservation(
                    ok=False,
                    content=str(exc),
                    metadata={"error": type(exc).__name__},
                )

        def timeout_observation() -> ToolObservation:
            return ToolObservation(
                ok=False,
                content="Tool exceeded per-tool time budget.",
                metadata={"error": "TimeoutError", "budget": "per_tool_seconds"},
            )

        parallel = self.can_parallelize(calls, tools)

        def collect_results(work: dict[str, Future[ToolObservation]]) -> list[ScheduledObservation]:
            observations: list[ScheduledObservation] = []
            for call in calls:
                if meter is not None:
                    meter.check_wall_clock()
                fut = work[call.id]
                try:
                    if per_tool_timeout is None:
                        obs = fut.result()
                    else:
                        obs = fut.result(timeout=per_tool_timeout)
                except FutureTimeoutError:
                    obs = timeout_observation()
                observations.append(ScheduledObservation(call=call, observation=obs))
            return observations

        if parallel:
            with ThreadPoolExecutor(max_workers=len(calls)) as pool:
                futures = {call.id: pool.submit(invoke, call) for call in calls}
                return collect_results(futures)

        with ThreadPoolExecutor(max_workers=1) as pool:
            futures = {call.id: pool.submit(invoke, call) for call in calls}
            return collect_results(futures)

"""Core Runtime."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import uuid4

from naqsha.approvals import ApprovalGate, StaticApprovalGate
from naqsha.budgets import BudgetExceeded, BudgetLimits, BudgetMeter
from naqsha.memory.base import MemoryPort
from naqsha.models.base import ModelClient
from naqsha.policy import PolicyDecisionKind, ToolPolicy
from naqsha.protocols.nap import NapAction, NapAnswer, nap_to_dict
from naqsha.protocols.qaoa import (
    TraceEvent,
    action_event,
    answer_event,
    failure_event,
    observation_event,
    query_event,
)
from naqsha.sanitizer import ObservationSanitizer
from naqsha.scheduler import ToolScheduler
from naqsha.tools.base import Tool, ToolObservation
from naqsha.trace.base import TraceStore


@dataclass
class RuntimeConfig:
    model: ModelClient
    tools: dict[str, Tool]
    trace_store: TraceStore
    policy: ToolPolicy
    budgets: BudgetLimits = field(default_factory=BudgetLimits)
    approval_gate: ApprovalGate = field(default_factory=StaticApprovalGate)
    sanitizer: ObservationSanitizer = field(default_factory=ObservationSanitizer)
    scheduler: ToolScheduler = field(default_factory=ToolScheduler)
    memory: MemoryPort | None = None
    memory_token_budget: int = 512


@dataclass(frozen=True)
class RunResult:
    run_id: str
    answer: str | None
    events: list[TraceEvent]
    failed: bool = False
    failure_code: str | None = None


class CoreRuntime:
    """Execute a single NAQSHA run with strict ports and guardrails."""

    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config

    def run(self, query: str, run_id: str | None = None) -> RunResult:
        run_id = run_id or str(uuid4())
        meter = BudgetMeter(self.config.budgets)
        events: list[TraceEvent] = []

        def persist(event: TraceEvent) -> None:
            self.config.trace_store.append(event)
            events.append(event)

        persist(query_event(run_id, query))
        if self.config.memory:
            self.config.memory.start_run(run_id, query)

        answer: str | None = None
        try:
            while answer is None:
                meter.consume_step()
                memory = (
                    self.config.memory.retrieve(query, self.config.memory_token_budget)
                    if self.config.memory
                    else []
                )
                message = self.config.model.next_message(
                    query=query,
                    trace=list(events),
                    tools=[tool.spec for tool in self.config.tools.values()],
                    memory=memory,
                )
                if isinstance(message, NapAnswer):
                    answer = message.text
                    persist(answer_event(run_id, answer))
                    break

                self._execute_action(message, run_id, persist, meter)
        except BudgetExceeded as exc:
            persist(failure_event(run_id, "budget_exceeded", str(exc)))
            return RunResult(
                run_id=run_id,
                answer=answer,
                events=events,
                failed=True,
                failure_code="budget_exceeded",
            )
        finally:
            if self.config.memory:
                self.config.memory.finish_run(run_id, answer)

        return RunResult(run_id=run_id, answer=answer, events=events)

    def _execute_action(
        self,
        action: NapAction,
        run_id: str,
        persist: Callable[[TraceEvent], None],
        meter: BudgetMeter,
    ) -> None:
        decisions = [
            self.config.policy.enforce(call, self.config.tools, self.config.approval_gate)
            for call in action.calls
        ]

        approved_calls = [
            call
            for call, decision in zip(action.calls, decisions, strict=True)
            if decision.decision == PolicyDecisionKind.ALLOW
        ]
        approved_tuple = tuple(approved_calls)
        parallel_eligible = (
            len(approved_tuple) > 1
            and self.config.scheduler.can_parallelize(approved_tuple, self.config.tools)
        )
        scheduler_meta = {
            "mode": "parallel" if parallel_eligible else "serial",
            "parallel_eligible": parallel_eligible,
        }

        persist(
            action_event(
                run_id,
                nap_to_dict(action),
                [decision.to_dict() for decision in decisions],
                scheduler=scheduler_meta,
            )
        )

        for call, decision in zip(action.calls, decisions, strict=True):
            if decision.decision == PolicyDecisionKind.ALLOW:
                continue
            denied = ToolObservation(
                ok=False,
                content=decision.reason,
                metadata={"policy": "denied"},
            )
            sanitized = self.config.sanitizer.sanitize(denied)
            persist(observation_event(run_id, call.id, call.name, sanitized.to_dict()))

        if not approved_calls:
            return

        for _ in approved_calls:
            meter.consume_tool_call()
        observations = self.config.scheduler.execute(
            approved_tuple, self.config.tools, meter=meter
        )
        for scheduled in observations:
            sanitized = self.config.sanitizer.sanitize(scheduled.observation)
            if self.config.memory:
                self.config.memory.record_observation(run_id, scheduled.call.name, sanitized)
            persist(
                observation_event(
                    run_id,
                    scheduled.call.id,
                    scheduled.call.name,
                    sanitized.to_dict(),
                )
            )

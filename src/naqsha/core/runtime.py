"""Core Runtime."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from uuid import uuid4

from naqsha.core.approvals import ApprovalGate, StaticApprovalGate
from naqsha.core.budgets import BudgetExceeded, BudgetLimits, BudgetMeter
from naqsha.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerTrippedError,
    circuit_failure_threshold,
)
from naqsha.core.event_bus import RuntimeEventBus
from naqsha.core.events import (
    BudgetProgress,
    CircuitBreakerTripped,
    RunCompleted,
    RunFailed,
    RunStarted,
    SpanClosed,
    SpanOpened,
    StreamChunkReceived,
    ToolCompleted,
    ToolErrored,
    ToolInvoked,
)
from naqsha.core.policy import PolicyDecisionKind, ToolPolicy
from naqsha.core.scheduler import ToolScheduler
from naqsha.memory.base import MemoryPort
from naqsha.memory.scope import MemoryScope
from naqsha.models.base import ModelClient
from naqsha.models.nap import NapAction, NapAnswer, nap_to_dict
from naqsha.tools.base import Tool, ToolObservation
from naqsha.tracing.protocols.qaoa import (
    TraceEvent,
    action_event,
    answer_event,
    failure_event,
    observation_event,
    query_event,
)
from naqsha.tracing.sanitizer import ObservationSanitizer
from naqsha.tracing.span import Span, SpanContext
from naqsha.tracing.store import TraceStore


class RunInterruptedError(Exception):
    """Raised when a cooperative interrupt is requested mid-run."""

    def __init__(self, message: str = "run_interrupted") -> None:
        self.message_text = message
        super().__init__(message)


def _chunk_answer_for_stream(text: str, *, chunk_size: int = 16) -> list[str]:
    """Split final answer text into pseudo-streaming chunks for the Typed Event Bus."""

    if not text:
        return []
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


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
    event_bus: RuntimeEventBus | None = None
    agent_id: str = "default"
    workspace_path: Path = field(default_factory=lambda: Path(".").resolve())
    trace_id: str | None = None
    span_context: SpanContext | None = None
    shared_memory_scope: MemoryScope | None = None
    private_memory_scope: MemoryScope | None = None
    #: Consecutive identical tool failures before tripping the circuit breaker.
    #: Values <= 0 trip immediately on the first identical failure streak.
    max_retries: int = 3
    #: Merged after the baseline NAQSHA system preamble in transcripts for adapters.
    agent_instructions: str = ""


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
        self._current_run_id: str | None = None
        self._active_span_context: SpanContext | None = None
        self._active_span: Span | None = None
        self._pause_continue = threading.Event()
        self._pause_continue.set()
        self._interrupt_flag = threading.Event()

    def request_pause(self) -> None:
        """Block the run loop at the next cooperative checkpoint until resumed."""

        self._pause_continue.clear()

    def request_resume(self) -> None:
        """Allow the run loop to proceed after pause."""

        self._pause_continue.set()

    def request_interrupt(self) -> None:
        """Stop the current run cleanly after the next checkpoint (budget-style failure)."""

        self._interrupt_flag.set()
        self._pause_continue.set()

    def _cooperative_checkpoint(self) -> None:
        self._pause_continue.wait()
        if self._interrupt_flag.is_set():
            raise RunInterruptedError()

    def _trace_kw(self) -> dict[str, str | None]:
        ctx = self._active_span_context
        if ctx is None:
            return {
                "trace_id": "",
                "span_id": "",
                "parent_span_id": None,
                "agent_id": self.config.agent_id or "default",
            }
        return {
            "trace_id": ctx.trace_id,
            "span_id": ctx.span_id,
            "parent_span_id": ctx.parent_span_id,
            "agent_id": ctx.agent_id,
        }

    def _make_agent_context(self):
        from naqsha.tools.context import AgentContext

        return AgentContext(
            shared_memory=self.config.shared_memory_scope,
            private_memory=self.config.private_memory_scope,
            span=self._active_span,
            workspace_path=self.config.workspace_path,
            agent_id=self.config.agent_id,
            run_id=self._current_run_id or "",
        )

    def _emit_budget_progress(self, run_id: str, agent_id: str, meter: BudgetMeter) -> None:
        bus = self.config.event_bus
        if not bus:
            return
        wall = monotonic() - meter.started_at
        bus.emit(
            BudgetProgress(
                run_id=run_id,
                agent_id=agent_id,
                steps_used=meter.steps,
                max_steps=meter.limits.max_steps,
                tool_calls_used=meter.tool_calls,
                max_tool_calls=meter.limits.max_tool_calls,
                wall_clock_used_seconds=wall,
                wall_clock_limit_seconds=meter.limits.wall_clock_seconds,
            )
        )

    def run(self, query: str, run_id: str | None = None) -> RunResult:
        run_id = run_id or str(uuid4())
        agent_id = self.config.agent_id or "default"
        meter = BudgetMeter(self.config.budgets)
        events: list[TraceEvent] = []

        trace_id = self.config.trace_id or run_id
        if self.config.span_context is not None:
            span_ctx = self.config.span_context
        else:
            span_ctx = SpanContext(
                trace_id=trace_id,
                span_id=str(uuid4()),
                parent_span_id=None,
                agent_id=agent_id,
            )

        self._current_run_id = run_id
        self._active_span_context = span_ctx
        self._active_span = Span(context=span_ctx)
        self._interrupt_flag.clear()
        self._pause_continue.set()

        if self.config.event_bus:
            self.config.event_bus.emit(
                RunStarted(run_id=run_id, agent_id=agent_id, query=query)
            )
            self.config.event_bus.emit(
                SpanOpened(
                    run_id=run_id,
                    trace_id=span_ctx.trace_id,
                    span_id=span_ctx.span_id,
                    parent_span_id=span_ctx.parent_span_id,
                    agent_id=span_ctx.agent_id,
                )
            )

        def persist(event: TraceEvent) -> None:
            self.config.trace_store.append(event)
            events.append(event)

        tk = self._trace_kw()
        persist(query_event(run_id, query, **tk))
        if self.config.memory:
            self.config.memory.start_run(run_id, query)

        answer: str | None = None
        failed = False
        failure_code: str | None = None
        failure_msg: str | None = None

        replay_mode = self.config.scheduler.recorded_observations is not None
        breaker_limit = circuit_failure_threshold(self.config.max_retries)
        circuit_breaker = None if replay_mode else CircuitBreaker(breaker_limit)

        instr = self.config.agent_instructions

        try:
            while answer is None:
                self._cooperative_checkpoint()
                meter.consume_step()
                if self.config.event_bus:
                    self._emit_budget_progress(run_id, agent_id, meter)
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
                    span_context=self._active_span_context,
                    instructions=instr,
                )
                if isinstance(message, NapAnswer):
                    answer = message.text
                    if self.config.event_bus and answer:
                        for piece in _chunk_answer_for_stream(answer):
                            self.config.event_bus.emit(
                                StreamChunkReceived(
                                    run_id=run_id, agent_id=agent_id, chunk=piece
                                )
                            )
                    persist(answer_event(run_id, answer, **self._trace_kw()))
                    break

                self._execute_action(
                    message, run_id, persist, meter, agent_id, circuit_breaker
                )
                if self.config.event_bus:
                    self._emit_budget_progress(run_id, agent_id, meter)
        except BudgetExceeded as exc:
            failed = True
            failure_code = "budget_exceeded"
            failure_msg = str(exc)
            persist(failure_event(run_id, failure_code, failure_msg, **self._trace_kw()))
            if self.config.event_bus:
                self.config.event_bus.emit(
                    RunFailed(
                        run_id=run_id,
                        agent_id=agent_id,
                        error_message=failure_msg,
                        total_steps=meter.steps,
                    )
                )
        except CircuitBreakerTrippedError as exc:
            failed = True
            failure_code = "circuit_breaker_tripped"
            failure_msg = str(exc)
            persist(failure_event(run_id, failure_code, failure_msg, **self._trace_kw()))
            if self.config.event_bus:
                self.config.event_bus.emit(
                    RunFailed(
                        run_id=run_id,
                        agent_id=agent_id,
                        error_message=failure_msg,
                        total_steps=meter.steps,
                    )
                )
        except RunInterruptedError as exc:
            failed = True
            failure_code = "interrupted"
            failure_msg = str(exc.message_text if hasattr(exc, "message_text") else exc)
            persist(failure_event(run_id, failure_code, failure_msg, **self._trace_kw()))
            if self.config.event_bus:
                self.config.event_bus.emit(
                    RunFailed(
                        run_id=run_id,
                        agent_id=agent_id,
                        error_message=failure_msg,
                        total_steps=meter.steps,
                    )
                )
        else:
            if self.config.event_bus:
                self.config.event_bus.emit(
                    RunCompleted(
                        run_id=run_id,
                        agent_id=agent_id,
                        answer=answer or "",
                        total_steps=meter.steps,
                        total_tokens=None,
                    )
                )
        finally:
            if self.config.memory:
                self.config.memory.finish_run(run_id, answer)
            if self.config.event_bus:
                span = self._active_span
                self.config.event_bus.emit(
                    SpanClosed(
                        run_id=run_id,
                        trace_id=span_ctx.trace_id,
                        span_id=span_ctx.span_id,
                        agent_id=span_ctx.agent_id,
                        token_count=span.token_count if span else None,
                        model_latency_ms=span.model_latency_ms if span else None,
                    )
                )
            self._current_run_id = None
            self._active_span_context = None
            self._active_span = None
            self._interrupt_flag.clear()
            self._pause_continue.set()

        if failed:
            return RunResult(
                run_id=run_id,
                answer=answer,
                events=events,
                failed=True,
                failure_code=failure_code,
            )
        return RunResult(run_id=run_id, answer=answer, events=events)

    def _execute_action(
        self,
        action: NapAction,
        run_id: str,
        persist: Callable[[TraceEvent], None],
        meter: BudgetMeter,
        agent_id: str,
        circuit_breaker: CircuitBreaker | None,
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

        tk = self._trace_kw()
        persist(
            action_event(
                run_id,
                nap_to_dict(action),
                [decision.to_dict() for decision in decisions],
                scheduler=scheduler_meta,
                **tk,
            )
        )

        for call, decision in zip(action.calls, decisions, strict=True):
            if decision.decision == PolicyDecisionKind.ALLOW:
                if self.config.event_bus:
                    self.config.event_bus.emit(
                        ToolInvoked(
                            run_id=run_id,
                            agent_id=agent_id,
                            tool_name=call.name,
                            call_id=call.id,
                            arguments=call.arguments,
                        )
                    )
                continue
            denied = ToolObservation(
                ok=False,
                content=decision.reason,
                metadata={"policy": "denied"},
            )
            sanitized = self.config.sanitizer.sanitize(denied)
            persist(observation_event(run_id, call.id, call.name, sanitized.to_dict(), **tk))
            if self.config.event_bus:
                self.config.event_bus.emit(
                    ToolErrored(
                        run_id=run_id,
                        agent_id=agent_id,
                        tool_name=call.name,
                        call_id=call.id,
                        error_message=decision.reason,
                    )
                )

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
                    **tk,
                )
            )
            if self.config.event_bus:
                if sanitized.ok:
                    self.config.event_bus.emit(
                        ToolCompleted(
                            run_id=run_id,
                            agent_id=agent_id,
                            tool_name=scheduled.call.name,
                            call_id=scheduled.call.id,
                            observation=sanitized.content,
                            execution_time_ms=None,
                        )
                    )
                else:
                    self.config.event_bus.emit(
                        ToolErrored(
                            run_id=run_id,
                            agent_id=agent_id,
                            tool_name=scheduled.call.name,
                            call_id=scheduled.call.id,
                            error_message=sanitized.content,
                        )
                    )
            if circuit_breaker is not None:
                streak = circuit_breaker.record(scheduled.call.name, sanitized)
                if circuit_breaker.should_trip(scheduled.call.name):
                    if self.config.event_bus:
                        self.config.event_bus.emit(
                            CircuitBreakerTripped(
                                run_id=run_id,
                                agent_id=agent_id,
                                tool_name=scheduled.call.name,
                                consecutive_failures=streak,
                            )
                        )
                    raise CircuitBreakerTrippedError(
                        tool_name=scheduled.call.name,
                        consecutive_failures=streak,
                    )

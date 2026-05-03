"""Circuit breaker thresholds and streak tracking."""

from __future__ import annotations

from pathlib import Path

import pytest

from naqsha.core.approvals import StaticApprovalGate
from naqsha.core.budgets import BudgetLimits
from naqsha.core.circuit_breaker import (
    CircuitBreaker,
    circuit_failure_threshold,
)
from naqsha.core.event_bus import RuntimeEventBus
from naqsha.core.events import CircuitBreakerTripped, ToolErrored
from naqsha.core.policy import ToolPolicy
from naqsha.models.fake import FakeModelClient
from naqsha.protocols.nap import NapAction, NapAnswer, ToolCall
from naqsha.runtime import CoreRuntime, RuntimeConfig
from naqsha.sanitizer import ObservationSanitizer
from naqsha.tools.base import FunctionTool, ToolObservation, ToolSpec
from naqsha.trace.jsonl import JsonlTraceStore


@pytest.mark.parametrize(
    ("raw", "threshold"),
    [
        (-3, 1),
        (0, 1),
        (1, 1),
        (3, 3),
    ],
)
def test_circuit_failure_threshold(raw: int, threshold: int) -> None:
    assert circuit_failure_threshold(raw) == threshold


def test_circuit_breaker_resets_after_success_same_tool() -> None:
    cb = CircuitBreaker(2)
    assert cb.record("t", ToolObservation(ok=False, content="a", metadata={"error": "E"})) == 1
    assert not cb.should_trip("t")
    assert cb.record("t", ToolObservation(ok=True, content="ok")) == 0
    assert cb.streak("t") == 0
    assert cb.record("t", ToolObservation(ok=False, content="a", metadata={"error": "E"})) == 1


def test_circuit_breaker_different_failure_content_resets_streak() -> None:
    cb = CircuitBreaker(2)
    assert cb.record("t", ToolObservation(ok=False, content="one", metadata={"error": "A"})) == 1
    assert cb.record("t", ToolObservation(ok=False, content="two", metadata={"error": "A"})) == 1
    assert not cb.should_trip("t")


def test_identical_failures_accumulate_until_trip() -> None:
    cb = CircuitBreaker(2)
    obs = ToolObservation(ok=False, content="boom", metadata={"error": "RuntimeError"})
    assert cb.record("t", obs) == 1
    assert cb.record("t", obs) == 2
    assert cb.should_trip("t")


def test_runtime_trips_records_failure_and_emit_bus(tmp_path: Path) -> None:
    """Two identical serialized tool failures exceed max_retries threshold."""

    def explode(arguments: dict[str, object]) -> ToolObservation:
        raise RuntimeError("same boom")

    boom = FunctionTool(
        ToolSpec(
            name="boom",
            description="boom",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        ),
        explode,
    )

    scripted = FakeModelClient(
        [
            NapAction(
                calls=(
                    ToolCall(id="a", name="boom", arguments={}),
                    ToolCall(id="b", name="boom", arguments={}),
                )
            ),
            NapAnswer(text="skipped"),
        ]
    )

    bus = RuntimeEventBus()
    received: list[type] = []

    bus.subscribe(lambda e: received.append(type(e)))

    rt = CoreRuntime(
        RuntimeConfig(
            model=scripted,
            tools={"boom": boom},
            trace_store=JsonlTraceStore(tmp_path / "tr"),
            policy=ToolPolicy(allowed_tools=frozenset({"boom"})),
            approval_gate=StaticApprovalGate(approved=True),
            sanitizer=ObservationSanitizer(max_chars=400),
            budgets=BudgetLimits(max_steps=20, max_tool_calls=20),
            max_retries=2,
            event_bus=bus,
        )
    )

    result = rt.run("q")
    assert result.failed
    assert result.failure_code == "circuit_breaker_tripped"

    failures = [e for e in result.events if e.kind == "failure"]
    assert failures[-1].payload["code"] == "circuit_breaker_tripped"

    assert CircuitBreakerTripped in received
    assert ToolErrored in received

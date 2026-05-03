"""Tool Policy, Approval Gate, Scheduler, and Budget guardrails."""

from __future__ import annotations

import json
import sys
import time
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from naqsha import cli
from naqsha.approvals import InteractiveApprovalGate, StaticApprovalGate
from naqsha.budgets import BudgetExceeded, BudgetLimits, BudgetMeter
from naqsha.models.fake import FakeModelClient
from naqsha.policy import PolicyDecisionKind, ToolPolicy
from naqsha.protocols.nap import NapAction, NapAnswer, ToolCall
from naqsha.protocols.qaoa import TraceEvent, TraceValidationError, action_event
from naqsha.runtime import CoreRuntime, RuntimeConfig
from naqsha.sanitizer import ObservationSanitizer
from naqsha.scheduler import ToolScheduler
from naqsha.tools.base import FunctionTool, Tool, ToolObservation, ToolSpec
from naqsha.tools.starter import starter_tools
from naqsha.trace.jsonl import JsonlTraceStore


def test_policy_allows_known_tool_with_readable_reason(tmp_path: Path) -> None:
    tools = starter_tools(tmp_path)
    policy = ToolPolicy.allow_all_starter_tools(tools)
    decision = policy.decide(ToolCall(id="a", name="clock", arguments={}), tools)
    assert decision.decision == PolicyDecisionKind.ALLOW
    assert decision.reason


def test_policy_denies_tool_not_on_allowlist(tmp_path: Path) -> None:
    tools = starter_tools(tmp_path)
    policy = ToolPolicy(allowed_tools=frozenset({"clock"}))
    decision = policy.decide(
        ToolCall(id="a", name="calculator", arguments={"expression": "1"}),
        tools,
    )
    assert decision.decision == PolicyDecisionKind.DENY
    assert "not allowed" in decision.reason


def test_policy_requires_approval_for_write_tier(tmp_path: Path) -> None:
    tools = starter_tools(tmp_path)
    policy = ToolPolicy.allow_all_starter_tools(tools)
    decision = policy.decide(
        ToolCall(id="w", name="write_file", arguments={"path": "a.txt", "content": "x"}),
        tools,
    )
    assert decision.decision == PolicyDecisionKind.REQUIRE_APPROVAL
    assert "risk tier" in decision.reason


def test_policy_enforce_denied_when_gate_rejects(tmp_path: Path) -> None:
    tools = starter_tools(tmp_path)
    policy = ToolPolicy.allow_all_starter_tools(tools)
    decision = policy.enforce(
        ToolCall(id="w", name="write_file", arguments={"path": "a.txt", "content": "x"}),
        tools,
        StaticApprovalGate(approved=False),
    )
    assert decision.decision == PolicyDecisionKind.DENY
    assert "Approval denied" in decision.reason


def test_interactive_gate_accepts_yes_token() -> None:
    gate = InteractiveApprovalGate()
    call = ToolCall(id="x", name="write_file", arguments={"path": "p", "content": "c"})
    spec = starter_tools(Path("."))["write_file"].spec
    old = sys.stdin
    try:
        sys.stdin = StringIO("yes\n")
        assert gate.approve(call, spec, "because") is True
    finally:
        sys.stdin = old


def test_scheduler_parallel_ineligible_when_duplicate_tool_names(tmp_path: Path) -> None:
    tools = starter_tools(tmp_path)
    sch = ToolScheduler()
    calls = (
        ToolCall(id="a", name="clock", arguments={}),
        ToolCall(id="b", name="clock", arguments={}),
    )
    assert sch.can_parallelize(calls, tools) is False


def test_scheduler_parallel_ineligible_when_write_mixed_in(tmp_path: Path) -> None:
    tools = starter_tools(tmp_path)
    sch = ToolScheduler()
    calls = (
        ToolCall(id="a", name="clock", arguments={}),
        ToolCall(id="b", name="write_file", arguments={"path": "x.txt", "content": "z"}),
    )
    assert sch.can_parallelize(calls, tools) is False


def test_scheduler_parallel_eligible_for_distinct_read_only_tools(tmp_path: Path) -> None:
    tools = starter_tools(tmp_path)
    sch = ToolScheduler()
    calls = (
        ToolCall(id="a", name="clock", arguments={}),
        ToolCall(id="b", name="calculator", arguments={"expression": "2+2"}),
    )
    assert sch.can_parallelize(calls, tools) is True


def test_scheduler_observation_order_matches_call_order_parallel(tmp_path: Path) -> None:
    tools = starter_tools(tmp_path)
    sch = ToolScheduler()
    calls = (
        ToolCall(id="first", name="calculator", arguments={"expression": "1"}),
        ToolCall(id="second", name="calculator", arguments={"expression": "2"}),
    )
    meter = BudgetMeter(BudgetLimits(per_tool_seconds=5.0))
    # Same tool name twice → serial mode; still assert ordering.
    assert sch.can_parallelize(calls, tools) is False
    out = sch.execute(calls, tools, meter=meter)
    assert [s.call.id for s in out] == ["first", "second"]


def test_scheduler_parallel_two_distinct_read_only_tools_trace_metadata(tmp_path: Path) -> None:
    tools = starter_tools(tmp_path)
    runtime = CoreRuntime(
        RuntimeConfig(
            model=FakeModelClient(
                [
                    NapAction(
                        calls=(
                            ToolCall(id="a", name="clock", arguments={}),
                            ToolCall(id="b", name="calculator", arguments={"expression": "3+1"}),
                        )
                    ),
                    NapAnswer(text="ok"),
                ]
            ),
            tools=tools,
            trace_store=JsonlTraceStore(tmp_path / "t"),
            policy=ToolPolicy.allow_all_starter_tools(tools),
            approval_gate=StaticApprovalGate(approved=True),
            sanitizer=ObservationSanitizer(max_chars=4000),
        )
    )
    result = runtime.run("q")
    action_ev = next(e for e in result.events if e.kind == "action")
    assert action_ev.payload["scheduler"]["parallel_eligible"] is True
    assert action_ev.payload["scheduler"]["mode"] == "parallel"


def test_multi_call_action_continues_after_tool_failure(tmp_path: Path) -> None:
    def boom(arguments: dict[str, object]) -> ToolObservation:
        if arguments["expression"] == "boom":
            raise ValueError("exploded")
        return ToolObservation(ok=True, content=str(arguments["expression"]))

    slow_tool = FunctionTool(
        ToolSpec(
            name="calc_x",
            description="test",
            parameters={
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
                "additionalProperties": False,
            },
        ),
        boom,
    )
    tools = {"calc_x": slow_tool}
    policy = ToolPolicy(allowed_tools=frozenset({"calc_x"}))
    runtime = CoreRuntime(
        RuntimeConfig(
            model=FakeModelClient(
                [
                    NapAction(
                        calls=(
                            ToolCall(id="1", name="calc_x", arguments={"expression": "fine"}),
                            ToolCall(id="2", name="calc_x", arguments={"expression": "boom"}),
                            ToolCall(id="3", name="calc_x", arguments={"expression": "after"}),
                        )
                    ),
                    NapAnswer(text="done"),
                ]
            ),
            tools=tools,
            trace_store=JsonlTraceStore(tmp_path / "t"),
            policy=policy,
            approval_gate=StaticApprovalGate(approved=True),
            sanitizer=ObservationSanitizer(max_chars=4000),
        )
    )
    result = runtime.run("x")
    obs = [e for e in result.events if e.kind == "observation"]
    assert len(obs) == 3
    assert obs[0].payload["observation"]["ok"] is True
    assert obs[1].payload["observation"]["ok"] is False
    assert "exploded" in obs[1].payload["observation"]["content"]
    assert obs[2].payload["observation"]["content"] == "after"


def test_per_tool_timeout_surfaces_as_failed_observation(tmp_path: Path) -> None:
    def slow(arguments: dict[str, object]) -> ToolObservation:
        time.sleep(0.2)
        return ToolObservation(ok=True, content="late")

    slow_tool = FunctionTool(
        ToolSpec(
            name="slow_op",
            description="test",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        ),
        slow,
    )
    tools_dict: dict[str, Tool] = {"slow_op": slow_tool}
    policy = ToolPolicy(allowed_tools=frozenset({"slow_op"}))
    runtime = CoreRuntime(
        RuntimeConfig(
            model=FakeModelClient(
                [
                    NapAction(calls=(ToolCall(id="s", name="slow_op", arguments={}),)),
                    NapAnswer(text="done"),
                ]
            ),
            tools=tools_dict,
            trace_store=JsonlTraceStore(tmp_path / "t"),
            policy=policy,
            budgets=BudgetLimits(per_tool_seconds=0.05, max_tool_calls=8, max_steps=8),
            approval_gate=StaticApprovalGate(approved=True),
            sanitizer=ObservationSanitizer(max_chars=4000),
        )
    )
    result = runtime.run("x")
    obs = next(e for e in result.events if e.kind == "observation")
    assert obs.payload["observation"]["ok"] is False
    assert "per-tool" in obs.payload["observation"]["content"].lower()


def test_budget_max_steps_emits_failure_event(tmp_path: Path) -> None:
    tools = starter_tools(tmp_path)
    runtime = CoreRuntime(
        RuntimeConfig(
            model=FakeModelClient(
                [
                    NapAction(calls=(ToolCall(id="c", name="clock", arguments={}),)),
                    NapAction(calls=(ToolCall(id="d", name="clock", arguments={}),)),
                ]
            ),
            tools=tools,
            trace_store=JsonlTraceStore(tmp_path / "t"),
            policy=ToolPolicy.allow_all_starter_tools(tools),
            budgets=BudgetLimits(max_steps=1),
            approval_gate=StaticApprovalGate(approved=True),
            sanitizer=ObservationSanitizer(max_chars=4000),
        )
    )
    result = runtime.run("loop")
    assert result.failed is True
    assert result.failure_code == "budget_exceeded"
    fail = next(e for e in result.events if e.kind == "failure")
    assert fail.payload["code"] == "budget_exceeded"


def test_budget_max_tool_calls_emits_failure_event(tmp_path: Path) -> None:
    tools = starter_tools(tmp_path)
    runtime = CoreRuntime(
        RuntimeConfig(
            model=FakeModelClient(
                [
                    NapAction(
                        calls=(
                            ToolCall(id="a", name="clock", arguments={}),
                            ToolCall(id="b", name="clock", arguments={}),
                        )
                    ),
                    NapAnswer(text="nope"),
                ]
            ),
            tools=tools,
            trace_store=JsonlTraceStore(tmp_path / "t"),
            policy=ToolPolicy.allow_all_starter_tools(tools),
            budgets=BudgetLimits(max_tool_calls=1),
            approval_gate=StaticApprovalGate(approved=True),
            sanitizer=ObservationSanitizer(max_chars=4000),
        )
    )
    result = runtime.run("two tools")
    assert result.failed is True
    assert result.answer is None


def test_budget_wall_clock_enforced_during_scheduled_tools(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Wall-clock checks run throughout the run; exhaustion fails closed."""

    hits = [0]
    _orig = BudgetMeter._check_wall_clock

    def wrapped(self: BudgetMeter) -> None:
        hits[0] += 1
        if hits[0] >= 6:
            raise BudgetExceeded("Wall-clock budget exceeded.")
        return _orig(self)

    monkeypatch.setattr(BudgetMeter, "_check_wall_clock", wrapped)

    tools = starter_tools(tmp_path)
    runtime = CoreRuntime(
        RuntimeConfig(
            model=FakeModelClient(
                [
                    NapAction(
                        calls=(
                            ToolCall(id="a", name="clock", arguments={}),
                            ToolCall(id="b", name="clock", arguments={}),
                            ToolCall(id="c", name="clock", arguments={}),
                        )
                    ),
                    NapAnswer(text="done"),
                ]
            ),
            tools=tools,
            trace_store=JsonlTraceStore(tmp_path / "t"),
            policy=ToolPolicy.allow_all_starter_tools(tools),
            budgets=BudgetLimits(wall_clock_seconds=3600.0, max_tool_calls=8, max_steps=8),
            approval_gate=StaticApprovalGate(approved=True),
            sanitizer=ObservationSanitizer(max_chars=4000),
        )
    )
    result = runtime.run("y")
    assert result.failed is True
    assert "Wall-clock" in next(e.payload["message"] for e in result.events if e.kind == "failure")


def test_budget_meter_check_wall_clock_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    meter = BudgetMeter(BudgetLimits(wall_clock_seconds=5.0))
    meter.started_at = 0.0
    monkeypatch.setattr("naqsha.budgets.monotonic", lambda: 100.0)
    with pytest.raises(BudgetExceeded, match="Wall-clock"):
        meter.check_wall_clock()


def test_cli_run_with_approve_prompt_allows_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    traces = tmp_path / "traces"
    traces.mkdir()
    profile_path = tmp_path / "p.json"
    profile_path.write_text(
        json.dumps(
            {
                "name": "prompt-test",
                "model": "fake",
                "trace_dir": str(traces),
                "tool_root": ".",
                "auto_approve": False,
                "fake_model": {
                    "messages": [
                        {
                            "kind": "action",
                            "calls": [
                                {
                                    "id": "w1",
                                    "name": "write_file",
                                    "arguments": {"path": "out.txt", "content": "hi"},
                                }
                            ],
                        },
                        {"kind": "answer", "text": "written"},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", StringIO("y\n"))
    buf = StringIO()
    with redirect_stdout(buf):
        code = cli.main(["run", "--profile", str(profile_path), "--approve-prompt", "q"])
    assert code == 0
    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "hi"


def test_trace_rejects_action_scheduler_bad_mode() -> None:
    raw = action_event(
        "r",
        {"kind": "action", "calls": []},
        [],
        scheduler={"mode": "magic"},
    ).to_dict()
    with pytest.raises(TraceValidationError, match="scheduler.mode"):
        TraceEvent.from_dict(raw)

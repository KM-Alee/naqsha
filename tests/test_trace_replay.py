"""Phase 7: deterministic trace replay (model script + recorded observations)."""

import pytest

from naqsha.approvals import StaticApprovalGate
from naqsha.cli import build_trace_replay_runtime
from naqsha.models.fake import FakeModelClient
from naqsha.policy import ToolPolicy
from naqsha.profiles import RunProfile
from naqsha.protocols.nap import NapAction, NapAnswer, ToolCall
from naqsha.protocols.qaoa import TraceEvent, observation_event
from naqsha.replay import (
    TraceReplayError,
    compare_replay,
    nap_messages_from_trace,
    observations_by_call_id,
    summarize_trace,
    tool_calls_chronology,
)
from naqsha.runtime import CoreRuntime, RuntimeConfig
from naqsha.sanitizer import ObservationSanitizer
from naqsha.scheduler import ReplayObservationMissing, ToolScheduler
from naqsha.tools.base import ToolObservation
from naqsha.tools.starter import starter_tools
from naqsha.trace.jsonl import JsonlTraceStore


def test_nap_messages_from_trace_round_trip(tmp_path) -> None:
    tools = starter_tools(tmp_path)
    rt = CoreRuntime(
        RuntimeConfig(
            model=FakeModelClient(
                [
                    NapAction(
                        calls=(ToolCall(id="c1", name="clock", arguments={}),),
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
    result = rt.run("ping")
    assert result.answer == "ok"
    events = JsonlTraceStore(tmp_path / "t").load(result.run_id)
    msgs = nap_messages_from_trace(events)
    assert len(msgs) == 2
    assert msgs[0].kind == "action"
    assert msgs[1].kind == "answer"


def test_replay_matches_reference_tool_path_and_answer(tmp_path) -> None:
    tools = starter_tools(tmp_path)
    trace_root = tmp_path / "traces"
    first = CoreRuntime(
        RuntimeConfig(
            model=FakeModelClient(
                [
                    NapAction(
                        calls=(
                            ToolCall(id="x1", name="calculator", arguments={"expression": "1+1"}),
                        ),
                    ),
                    NapAnswer(text="two"),
                ]
            ),
            tools=tools,
            trace_store=JsonlTraceStore(trace_root),
            policy=ToolPolicy.allow_all_starter_tools(tools),
            approval_gate=StaticApprovalGate(approved=True),
            sanitizer=ObservationSanitizer(max_chars=4000),
        )
    )
    res = first.run("math")
    reference = JsonlTraceStore(trace_root).load(res.run_id)
    assert summarize_trace(JsonlTraceStore(trace_root), res.run_id).answer == "two"

    profile = RunProfile(
        name="replay-test",
        trace_dir=trace_root,
        tool_root=tmp_path,
        model="fake",
        fake_model_messages=({"kind": "answer", "text": "ignored"},),
        auto_approve=True,
    )
    second = build_trace_replay_runtime(profile, reference)
    replay_result = second.run("math")
    assert not replay_result.failed
    assert replay_result.answer == "two"

    replay_events = JsonlTraceStore(trace_root).load(replay_result.run_id)
    diff = compare_replay(reference, replay_events)
    assert diff.answer_matches
    assert diff.tool_calls_match
    assert tool_calls_chronology(reference) == [{"call_id": "x1", "tool": "calculator"}]


def test_scheduler_replay_missing_observation_raises(tmp_path) -> None:
    tools = starter_tools(tmp_path)
    sch = ToolScheduler(
        recorded_observations={
            "other": ToolObservation(ok=True, content="no"),
        }
    )
    calls = (ToolCall(id="missing", name="clock", arguments={}),)
    with pytest.raises(ReplayObservationMissing):
        sch.execute(calls, tools)


def test_observations_by_call_id_rejects_duplicates() -> None:
    run_id = "r1"
    obs: dict[str, object] = {"ok": True, "content": "x", "metadata": {}}
    events = [
        TraceEvent(kind="query", run_id=run_id, payload={"query": "q"}),
        observation_event(run_id, "c1", "clock", obs),
        observation_event(run_id, "c1", "clock", obs),
    ]
    with pytest.raises(TraceReplayError, match="Duplicate"):
        observations_by_call_id(events)

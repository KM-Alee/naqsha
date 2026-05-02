import json

import pytest

from naqsha.approvals import StaticApprovalGate
from naqsha.models.fake import FakeModelClient
from naqsha.policy import PolicyDecisionKind, ToolPolicy
from naqsha.protocols.nap import NapAction, NapAnswer, ToolCall, nap_to_dict
from naqsha.protocols.qaoa import (
    QAOA_TRACE_SCHEMA_VERSION,
    TraceEvent,
    TraceValidationError,
    answer_event,
    observation_event,
    query_event,
)
from naqsha.replay import summarize_trace
from naqsha.runtime import CoreRuntime, RuntimeConfig
from naqsha.sanitizer import ObservationSanitizer
from naqsha.tools.starter import starter_tools
from naqsha.trace.jsonl import JsonlTraceStore


def test_policy_denies_unknown_tool(tmp_path) -> None:
    tools = starter_tools(tmp_path)
    policy = ToolPolicy.allow_all_starter_tools(tools)

    decision = policy.decide(ToolCall(id="x", name="not_a_real_tool", arguments={}), tools)

    assert decision.decision == PolicyDecisionKind.DENY
    assert "Unknown tool" in decision.reason


def test_policy_denies_invalid_arguments(tmp_path) -> None:
    tools = starter_tools(tmp_path)
    policy = ToolPolicy.allow_all_starter_tools(tools)

    decision = policy.decide(
        ToolCall(id="calc-1", name="calculator", arguments={"unexpected": "2+2"}),
        tools,
    )

    assert decision.decision == PolicyDecisionKind.DENY
    assert "Missing required" in decision.reason


def test_policy_approval_can_allow_write_tool(tmp_path) -> None:
    tools = starter_tools(tmp_path)
    policy = ToolPolicy.allow_all_starter_tools(tools)

    decision = policy.enforce(
        ToolCall(id="write-1", name="write_file", arguments={"path": "x.txt", "content": "x"}),
        tools,
        StaticApprovalGate(approved=True),
    )

    assert decision.decision == PolicyDecisionKind.ALLOW
    assert decision.reason == "Approved."


def test_jsonl_trace_store_rejects_corrupted_lines(tmp_path) -> None:
    store = JsonlTraceStore(tmp_path)
    store.append(query_event("run-1", "hello"))
    (tmp_path / "run-1.jsonl").write_text("{bad json\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Corrupted trace line"):
        store.load("run-1")


def test_jsonl_trace_store_preserves_event_order(tmp_path) -> None:
    store = JsonlTraceStore(tmp_path)
    first = query_event("run-order", "one")
    second = query_event("run-order", "two")
    store.append(first)
    store.append(second)

    loaded = store.load("run-order")

    assert [event.payload["query"] for event in loaded] == ["one", "two"]
    assert loaded[0].event_id != loaded[1].event_id


def test_jsonl_trace_store_rejects_semantically_invalid_line(tmp_path) -> None:
    store = JsonlTraceStore(tmp_path)
    valid = query_event("run-bad", "ok").to_dict()
    invalid_observation = {
        "schema_version": QAOA_TRACE_SCHEMA_VERSION,
        "kind": "observation",
        "event_id": "e1",
        "run_id": "run-bad",
        "created_at": "2020-01-01T00:00:00+00:00",
        "payload": {"call_id": "c1", "tool": "t"},
    }
    path = tmp_path / "run-bad.jsonl"
    path.write_text(
        json.dumps(valid, sort_keys=True)
        + "\n"
        + json.dumps(invalid_observation, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Corrupted trace line"):
        store.load("run-bad")


def test_replay_summary_loads_observations_and_answer(tmp_path) -> None:
    store = JsonlTraceStore(tmp_path)
    run_id = "run-replay"
    store.append(query_event(run_id, "q"))
    store.append(
        TraceEvent(
            kind="action",
            run_id=run_id,
            payload={
                "action": nap_to_dict(
                    NapAction(
                        calls=(ToolCall(id="c1", name="clock", arguments={}),),
                    )
                ),
                "policy": [],
            },
        )
    )
    store.append(
        observation_event(run_id, "c1", "clock", {"ok": True, "content": "tick", "metadata": {}})
    )
    store.append(answer_event(run_id, "done"))

    summary = summarize_trace(store, run_id)

    assert summary.queries == ["q"]
    assert summary.answer == "done"
    assert len(summary.observations) == 1


def test_trace_file_observations_are_post_sanitizer(tmp_path) -> None:
    """Redaction boundary: persisted observations match sanitizer output, not raw tool output."""

    tools = starter_tools(tmp_path)
    trace_root = tmp_path / "traces"
    runtime = CoreRuntime(
        RuntimeConfig(
            model=FakeModelClient(
                [
                    NapAction(
                        calls=(
                            ToolCall(
                                id="read-1",
                                name="read_file",
                                arguments={"path": "secret.txt"},
                            ),
                        )
                    ),
                    NapAnswer(text="done"),
                ]
            ),
            tools=tools,
            trace_store=JsonlTraceStore(trace_root),
            policy=ToolPolicy.allow_all_starter_tools(tools),
            approval_gate=StaticApprovalGate(approved=True),
            sanitizer=ObservationSanitizer(max_chars=80),
        )
    )
    secret_line = "token=sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    (tmp_path / "secret.txt").write_text(secret_line, encoding="utf-8")

    result = runtime.run("read secret")
    assert result.answer == "done"

    disk_events = JsonlTraceStore(trace_root).load(result.run_id)
    obs_events = [e for e in disk_events if e.kind == "observation"]
    assert len(obs_events) == 1
    content = obs_events[0].payload["observation"]["content"]
    assert "sk-" not in content
    assert "[redacted]" in content.lower()


def test_trace_validation_error_message_for_bad_payload() -> None:
    raw = query_event("r", "x").to_dict()
    raw["payload"] = "not-an-object"

    with pytest.raises(TraceValidationError, match="object"):
        TraceEvent.from_dict(raw)

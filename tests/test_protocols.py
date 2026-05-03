import json

import pytest

from naqsha.models.nap import nap_to_dict
from naqsha.protocols.nap import NapAction, NapAnswer, NapValidationError, parse_nap_message
from naqsha.protocols.qaoa import (
    QAOA_TRACE_SCHEMA_VERSION,
    TraceEvent,
    TraceValidationError,
    answer_event,
    failure_event,
    observation_event,
    query_event,
)
from naqsha.tracing.span import SpanContext


def test_parse_final_answer() -> None:
    message = parse_nap_message({"kind": "answer", "text": "done"})

    assert message == NapAnswer(text="done")


def test_parse_answer_with_span_context_round_trip() -> None:
    ctx = SpanContext(
        trace_id="tr",
        span_id="sp",
        parent_span_id=None,
        agent_id="a1",
    )
    msg = parse_nap_message(
        {
            "kind": "answer",
            "text": "hi",
            "span_context": {
                "trace_id": "tr",
                "span_id": "sp",
                "parent_span_id": None,
                "agent_id": "a1",
            },
        }
    )
    assert isinstance(msg, NapAnswer)
    assert msg.span_context == ctx
    again = parse_nap_message(nap_to_dict(msg))
    assert again == msg


def test_parse_action_with_span_context() -> None:
    msg = parse_nap_message(
        {
            "kind": "action",
            "calls": [{"id": "c1", "name": "clock", "arguments": {}}],
            "span_context": {
                "trace_id": "t",
                "span_id": "s",
                "parent_span_id": "p",
                "agent_id": "w",
            },
        }
    )
    assert isinstance(msg, NapAction)
    assert msg.span_context is not None
    assert msg.span_context.parent_span_id == "p"


def test_parse_action_rejects_duplicate_call_ids() -> None:
    with pytest.raises(NapValidationError, match="Duplicate"):
        parse_nap_message(
            {
                "kind": "action",
                "calls": [
                    {"id": "same", "name": "clock", "arguments": {}},
                    {"id": "same", "name": "calculator", "arguments": {"expression": "1+1"}},
                ],
            }
        )


def test_parse_action_rejects_unexpected_chain_of_thought_field() -> None:
    with pytest.raises(NapValidationError, match="Unexpected"):
        parse_nap_message({"kind": "answer", "text": "done", "reasoning": "private"})


def test_parse_action_rejects_thought_field_on_action() -> None:
    with pytest.raises(NapValidationError, match="Unexpected"):
        parse_nap_message(
            {
                "kind": "action",
                "calls": [{"id": "a", "name": "clock", "arguments": {}}],
                "chain_of_thought": "hidden",
            }
        )


def test_parse_action() -> None:
    message = parse_nap_message(
        {
            "kind": "action",
            "calls": [{"id": "calc-1", "name": "calculator", "arguments": {"expression": "2+2"}}],
        }
    )

    assert isinstance(message, NapAction)
    assert message.calls[0].name == "calculator"


def test_parse_rejects_non_object_payload() -> None:
    with pytest.raises(NapValidationError, match="JSON object"):
        parse_nap_message([])  # type: ignore[arg-type]


def test_parse_rejects_non_string_kind() -> None:
    with pytest.raises(NapValidationError, match="kind must be a string"):
        parse_nap_message({"kind": 1, "text": "x"})  # type: ignore[dict-item]


def test_parse_rejects_unknown_kind_string() -> None:
    with pytest.raises(NapValidationError, match="'action' or 'answer'"):
        parse_nap_message({"kind": "tool_use", "text": "x"})


def test_parse_action_rejects_empty_calls() -> None:
    with pytest.raises(NapValidationError, match="one or more calls"):
        parse_nap_message({"kind": "action", "calls": []})


def test_parse_action_rejects_calls_not_list() -> None:
    with pytest.raises(NapValidationError, match="one or more calls"):
        parse_nap_message({"kind": "action", "calls": {}})  # type: ignore[dict-item]


def test_parse_action_rejects_call_not_object() -> None:
    with pytest.raises(NapValidationError, match="object"):
        parse_nap_message({"kind": "action", "calls": ["not-a-dict"]})


def test_parse_action_rejects_unexpected_fields_in_call() -> None:
    with pytest.raises(NapValidationError, match="unexpected fields"):
        parse_nap_message(
            {
                "kind": "action",
                "calls": [{"id": "a", "name": "clock", "arguments": {}, "reasoning": "no"}],
            }
        )


def test_parse_action_rejects_whitespace_only_call_id() -> None:
    with pytest.raises(NapValidationError, match="whitespace"):
        parse_nap_message(
            {"kind": "action", "calls": [{"id": "   ", "name": "clock", "arguments": {}}]}
        )


def test_parse_action_rejects_call_id_with_leading_whitespace() -> None:
    with pytest.raises(NapValidationError, match="leading or trailing whitespace"):
        parse_nap_message(
            {"kind": "action", "calls": [{"id": " x", "name": "clock", "arguments": {}}]}
        )


def test_parse_action_rejects_call_id_with_newline() -> None:
    with pytest.raises(NapValidationError, match="forbidden"):
        parse_nap_message(
            {"kind": "action", "calls": [{"id": "a\nb", "name": "clock", "arguments": {}}]}
        )


def test_parse_action_rejects_oversized_call_id() -> None:
    long_id = "x" * 257
    with pytest.raises(NapValidationError, match="maximum length"):
        parse_nap_message(
            {"kind": "action", "calls": [{"id": long_id, "name": "clock", "arguments": {}}]}
        )


def test_parse_action_rejects_non_string_argument_keys() -> None:
    with pytest.raises(NapValidationError, match="string keys"):
        parse_nap_message(
            {
                "kind": "action",
                "calls": [{"id": "a", "name": "clock", "arguments": {1: "bad"}}],  # type: ignore[dict-item]
            }
        )


def test_parse_answer_rejects_empty_text() -> None:
    with pytest.raises(NapValidationError, match="non-empty text"):
        parse_nap_message({"kind": "answer", "text": ""})


def test_trace_event_roundtrip_includes_schema_version() -> None:
    event = query_event("run-1", "hello")
    data = event.to_dict()

    assert data["schema_version"] == QAOA_TRACE_SCHEMA_VERSION
    assert TraceEvent.from_dict(data) == event


def test_trace_event_from_dict_defaults_missing_schema_version() -> None:
    event = query_event("run-1", "hello")
    legacy = {k: v for k, v in event.to_dict().items() if k != "schema_version"}
    loaded = TraceEvent.from_dict(legacy)

    assert loaded.schema_version == 1
    assert loaded.kind == "query"
    assert loaded.payload == {"query": "hello"}


def test_trace_event_from_dict_rejects_unknown_top_level_field() -> None:
    event = query_event("run-1", "hello").to_dict()
    bad = {**event, "extra": 1}

    with pytest.raises(TraceValidationError, match="Unexpected trace fields"):
        TraceEvent.from_dict(bad)


def test_trace_event_from_dict_rejects_unsupported_schema_version() -> None:
    event = query_event("run-1", "hello").to_dict()
    bad = {**event, "schema_version": 999}

    with pytest.raises(TraceValidationError, match="Unsupported"):
        TraceEvent.from_dict(bad)


def test_trace_event_from_dict_rejects_non_integer_schema_version() -> None:
    base = query_event("run-1", "hello").to_dict()
    with pytest.raises(TraceValidationError, match="Unsupported"):
        TraceEvent.from_dict({**base, "schema_version": True})
    with pytest.raises(TraceValidationError, match="Unsupported"):
        TraceEvent.from_dict({**base, "schema_version": 1.0})


def test_trace_event_from_dict_rejects_invalid_kind() -> None:
    base = query_event("run-1", "hello").to_dict()
    bad = {**base, "kind": "thinking"}

    with pytest.raises(TraceValidationError, match="Invalid trace event kind"):
        TraceEvent.from_dict(bad)


def test_trace_event_payload_validation_observation() -> None:
    good = observation_event("r", "c1", "clock", {"ok": True, "content": "x"}).to_dict()
    TraceEvent.from_dict(good)

    bad = {**good, "payload": {"call_id": "c1", "tool": "clock"}}
    with pytest.raises(TraceValidationError, match="missing"):
        TraceEvent.from_dict(bad)


def test_trace_event_payload_validation_failure() -> None:
    good = failure_event("r", "budget_exceeded", "out of budget").to_dict()
    TraceEvent.from_dict(good)

    bad = {**good, "payload": {"code": "x", "message": 1}}
    with pytest.raises(TraceValidationError, match="Failure payload"):
        TraceEvent.from_dict(bad)


def test_trace_event_json_roundtrip() -> None:
    event = answer_event("run-z", "final")
    line = json.dumps(event.to_dict(), sort_keys=True)
    loaded = TraceEvent.from_dict(json.loads(line))

    assert loaded == event

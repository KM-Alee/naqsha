"""Tests for provider-neutral trace → transcript mapping."""

from __future__ import annotations

from naqsha.memory.base import MemoryRecord
from naqsha.models.trace_turns import (
    trace_to_transcript,
    transcript_to_anthropic_messages,
    transcript_to_gemini_contents,
    transcript_to_openai_chat_messages,
)
from naqsha.protocols.qaoa import action_event, observation_event, query_event


def test_transcript_matches_openai_roles_after_tool_round() -> None:
    trace = [
        query_event("r", "hi"),
        action_event(
            "r",
            {"kind": "action", "calls": [{"id": "t1", "name": "clock", "arguments": {}}]},
            policy=[],
        ),
        observation_event(
            "r",
            "t1",
            "clock",
            {"ok": True, "content": "noon", "metadata": {}},
        ),
    ]
    t = trace_to_transcript(query="hi", trace=trace, memory=[])
    oa = transcript_to_openai_chat_messages(t)
    assert oa[0]["role"] == "system"
    assert oa[1]["role"] == "user"
    assert oa[2]["role"] == "assistant"
    assert oa[2]["tool_calls"][0]["function"]["name"] == "clock"
    assert oa[3]["role"] == "tool"


def test_anthropic_system_is_split_from_messages() -> None:
    trace = [query_event("r", "yo")]
    mem = [MemoryRecord(content="m", provenance="p")]
    t = trace_to_transcript(query="yo", trace=trace, memory=mem)
    system, msgs = transcript_to_anthropic_messages(t)
    assert "NAQSHA" in system
    assert "m" in system
    assert msgs == [{"role": "user", "content": "yo"}]


def test_gemini_uses_model_role_for_tool_calls() -> None:
    trace = [
        query_event("r", "hi"),
        action_event(
            "r",
            {"kind": "action", "calls": [{"id": "id1", "name": "clock", "arguments": {}}]},
            policy=[],
        ),
        observation_event("r", "id1", "clock", {"ok": True, "content": "z", "metadata": {}}),
    ]
    t = trace_to_transcript(query="hi", trace=trace, memory=[])
    _sys, contents = transcript_to_gemini_contents(t)
    assert contents[1]["role"] == "model"
    assert "functionCall" in contents[1]["parts"][0]
    assert contents[2]["parts"][0]["functionResponse"]["name"] == "clock"

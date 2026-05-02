"""Tests for OpenAI-compatible ModelClient adapter (mocked HTTP only)."""

from __future__ import annotations

import json

import pytest

from naqsha.memory.base import MemoryRecord
from naqsha.models.errors import ModelInvocationError
from naqsha.models.openai_compat import OpenAiCompatModelClient, trace_to_chat_messages
from naqsha.protocols.nap import NapAction, NapAnswer, ToolCall
from naqsha.protocols.qaoa import (
    action_event,
    observation_event,
    query_event,
)
from naqsha.tools.base import RiskTier, ToolSpec


def _tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="clock",
            description="time",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            risk_tier=RiskTier.READ_ONLY,
            read_only=True,
        )
    ]


def test_trace_to_chat_messages_query_only() -> None:
    trace = [query_event("r1", "What time?")]
    msgs = trace_to_chat_messages(query="ignored-if-trace-has-query", trace=trace, memory=[])
    assert msgs[0]["role"] == "system"
    assert msgs[1] == {"role": "user", "content": "What time?"}


def test_trace_to_chat_messages_includes_memory_preface() -> None:
    trace = [query_event("r1", "Hi")]
    mem = [MemoryRecord(content="fact", provenance="run:abc")]
    msgs = trace_to_chat_messages(query="Hi", trace=trace, memory=mem)
    assert "untrusted" in msgs[0]["content"].lower()
    assert "run:abc" in msgs[0]["content"]
    assert "fact" in msgs[0]["content"]


def test_trace_to_chat_messages_action_and_observations_round_trip() -> None:
    trace = [
        query_event("r1", "tick"),
        action_event(
            "r1",
            {
                "kind": "action",
                "calls": [{"id": "c1", "name": "clock", "arguments": {}}],
            },
            policy=[],
        ),
        observation_event(
            "r1",
            "c1",
            "clock",
            {"ok": True, "content": "noon", "metadata": {}},
        ),
    ]
    msgs = trace_to_chat_messages(query="tick", trace=trace, memory=[])
    assert msgs[2]["role"] == "assistant"
    assert msgs[2]["tool_calls"][0]["function"]["name"] == "clock"
    assert msgs[3]["role"] == "tool"
    assert msgs[3]["tool_call_id"] == "c1"
    assert "noon" in msgs[3]["content"]


def test_next_message_maps_tool_calls_to_nap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")

    def fake_post(
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]:
        assert "/chat/completions" in url
        assert "Bearer sk-test-dummy" == headers.get("Authorization")
        parsed = json.loads(body.decode())
        assert parsed["temperature"] == 0
        assert parsed["tool_choice"] == "auto"
        assert len(parsed["tools"]) >= 1
        resp = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_z",
                                "type": "function",
                                "function": {"name": "clock", "arguments": "{}"},
                            }
                        ],
                    }
                }
            ]
        }
        return 200, json.dumps(resp).encode()

    client = OpenAiCompatModelClient(
        base_url="https://example.invalid/v1",
        model="mock-model",
        post_fn=fake_post,
    )
    msg = client.next_message(
        query="q",
        trace=[query_event("rid", "q")],
        tools=_tool_specs(),
        memory=[],
    )
    assert isinstance(msg, NapAction)
    assert msg.calls == (
        ToolCall(id="call_z", name="clock", arguments={}),
    )


def test_next_message_maps_content_to_nap_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")

    def fake_post(
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]:
        resp = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "  Done. ",
                    }
                }
            ]
        }
        return 200, json.dumps(resp).encode()

    client = OpenAiCompatModelClient(
        base_url="https://x/v1",
        model="m",
        post_fn=fake_post,
    )
    msg = client.next_message(
        query="q",
        trace=[query_event("r", "q")],
        tools=_tool_specs(),
        memory=[],
    )
    assert msg == NapAnswer(text="Done.")


def test_next_message_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = OpenAiCompatModelClient(base_url="https://x/v1", model="m")
    with pytest.raises(ModelInvocationError, match="OPENAI_API_KEY"):
        client.next_message(
            query="q",
            trace=[query_event("r", "q")],
            tools=_tool_specs(),
            memory=[],
        )


def test_next_message_surfaces_http_error_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")

    def fake_post(
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]:
        return 401, json.dumps({"error": {"message": "bad key"}}).encode()

    client = OpenAiCompatModelClient(base_url="https://x/v1", model="m", post_fn=fake_post)
    with pytest.raises(ModelInvocationError, match="401"):
        client.next_message(
            query="q",
            trace=[query_event("r", "q")],
            tools=_tool_specs(),
            memory=[],
        )


def test_error_redacts_authorization_header_in_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret-token-value")

    def fake_post(
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]:
        return 500, b'{"error":{"message":"oops"}}'

    client = OpenAiCompatModelClient(base_url="https://x/v1", model="m", post_fn=fake_post)
    with pytest.raises(ModelInvocationError) as excinfo:
        client.next_message(
            query="q",
            trace=[query_event("r", "q")],
            tools=_tool_specs(),
            memory=[],
        )
    assert "secret-token-value" not in str(excinfo.value)
    assert "<redacted>" in str(excinfo.value)


def test_invalid_provider_tool_arguments_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")

    def fake_post(
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]:
        resp = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "x",
                                "type": "function",
                                "function": {"name": "clock", "arguments": "not-json"},
                            }
                        ],
                    }
                }
            ]
        }
        return 200, json.dumps(resp).encode()

    client = OpenAiCompatModelClient(base_url="https://x/v1", model="m", post_fn=fake_post)
    with pytest.raises(ModelInvocationError, match="not valid JSON"):
        client.next_message(
            query="q",
            trace=[query_event("r", "q")],
            tools=_tool_specs(),
            memory=[],
        )

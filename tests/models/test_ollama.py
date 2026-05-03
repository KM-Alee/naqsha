"""Ollama ModelClient adapter (mocked HTTP only)."""

from __future__ import annotations

import json

import pytest

from naqsha.models.errors import ModelInvocationError
from naqsha.models.ollama import OllamaChatModelClient
from naqsha.models.openai_compat import trace_to_chat_messages
from naqsha.protocols.nap import NapAction, NapAnswer
from naqsha.protocols.qaoa import query_event
from naqsha.tools.base import RiskTier, ToolSpec
from naqsha.tracing.span import SpanContext


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


def test_trace_to_chat_messages_ollama_path() -> None:
    trace = [query_event("r1", "What time?")]
    msgs = trace_to_chat_messages(query="ignored-if-trace-has-query", trace=trace, memory=[])
    assert msgs[0]["role"] == "system"
    assert msgs[1] == {"role": "user", "content": "What time?"}


def test_next_message_maps_ollama_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]:
        assert "/api/chat" in url
        assert "Authorization" not in headers
        parsed = json.loads(body.decode())
        assert parsed["stream"] is False
        assert parsed["model"] == "mistral"
        assert parsed["options"]["temperature"] == 0
        resp = {
            "model": "mistral",
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_z",
                        "type": "function",
                        "function": {"name": "clock", "arguments": "{}"},
                    }
                ],
            },
            "done": True,
        }
        return (200, json.dumps(resp).encode())

    client = OllamaChatModelClient(
        base_url="http://127.0.0.1:11434",
        model="mistral",
        post_fn=fake_post,
    )
    span = SpanContext(
        trace_id="t-1",
        span_id="s-1",
        parent_span_id=None,
        agent_id="agent-a",
    )
    msg = client.next_message(
        query="hi",
        trace=[query_event("r1", "hi")],
        tools=_tool_specs(),
        memory=[],
        span_context=span,
    )
    assert isinstance(msg, NapAction)
    assert msg.calls[0].name == "clock"
    assert msg.span_context == span


def test_next_message_maps_ollama_text_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]:
        return (
            200,
            json.dumps(
                {
                    "message": {"role": "assistant", "content": "  hello from ollama  "},
                    "done": True,
                }
            ).encode(),
        )

    client = OllamaChatModelClient(base_url="http://localhost:11434", model="m", post_fn=fake_post)
    span = SpanContext(
        trace_id="t-2",
        span_id="s-2",
        parent_span_id="p-1",
        agent_id="b",
    )
    msg = client.next_message(
        query="x",
        trace=[query_event("r", "x")],
        tools=_tool_specs(),
        memory=[],
        span_context=span,
    )
    assert isinstance(msg, NapAnswer)
    assert msg.text == "hello from ollama"
    assert msg.span_context == span


def test_next_message_sends_bearer_when_api_key_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_TEST_KEY", "secret-token")

    def fake_post(
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]:
        assert headers.get("Authorization") == "Bearer secret-token"
        body = {"message": {"role": "assistant", "content": "ok"}, "done": True}
        return (200, json.dumps(body).encode())

    client = OllamaChatModelClient(
        base_url="http://x",
        model="m",
        api_key_env="OLLAMA_TEST_KEY",
        post_fn=fake_post,
    )
    msg = client.next_message(
        query="q",
        trace=[query_event("r", "q")],
        tools=_tool_specs(),
        memory=[],
    )
    assert isinstance(msg, NapAnswer)


def test_next_message_requires_api_key_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_OLLAMA_KEY", raising=False)
    client = OllamaChatModelClient(
        base_url="http://x",
        model="m",
        api_key_env="MISSING_OLLAMA_KEY",
        post_fn=lambda u, h, b, t: (200, b"{}"),
    )
    with pytest.raises(ModelInvocationError, match="MISSING_OLLAMA_KEY"):
        client.next_message(
            query="q",
            trace=[query_event("r", "q")],
            tools=_tool_specs(),
            memory=[],
        )


def test_next_message_surfaces_missing_message(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]:
        return (200, json.dumps({"done": True}).encode())

    client = OllamaChatModelClient(base_url="http://x", model="m", post_fn=fake_post)
    with pytest.raises(ModelInvocationError, match="message object"):
        client.next_message(
            query="q",
            trace=[query_event("r", "q")],
            tools=_tool_specs(),
            memory=[],
        )

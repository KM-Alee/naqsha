"""Anthropic Messages adapter tests (mocked HTTP)."""

from __future__ import annotations

import json

import pytest

from naqsha.models.anthropic import AnthropicMessagesModelClient
from naqsha.models.errors import ModelInvocationError
from naqsha.protocols.nap import NapAction, NapAnswer, ToolCall
from naqsha.protocols.qaoa import query_event
from naqsha.tools.base import RiskTier, ToolSpec


def _specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="clock",
            description="t",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            risk_tier=RiskTier.READ_ONLY,
            read_only=True,
        )
    ]


def test_tool_use_maps_to_nap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")

    def fake_post(
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]:
        assert "/v1/messages" in url
        assert headers.get("anthropic-version") == "2023-06-01"
        payload = json.loads(body.decode())
        assert payload["temperature"] == 0
        assert payload["tools"][0]["name"] == "clock"
        resp = {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "tu_01", "name": "clock", "input": {}},
            ],
            "stop_reason": "tool_use",
        }
        return 200, json.dumps(resp).encode()

    client = AnthropicMessagesModelClient(
        base_url="https://example.invalid",
        model="claude-test",
        post_fn=fake_post,
    )
    msg = client.next_message(
        query="q",
        trace=[query_event("r", "q")],
        tools=_specs(),
        memory=[],
    )
    assert msg == NapAction(calls=(ToolCall(id="tu_01", name="clock", arguments={}),))


def test_text_content_maps_to_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")

    def fake_post(
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]:
        resp = {
            "role": "assistant",
            "content": [{"type": "text", "text": "Final answer."}],
            "stop_reason": "end_turn",
        }
        return 200, json.dumps(resp).encode()

    client = AnthropicMessagesModelClient(
        base_url="https://x",
        model="m",
        post_fn=fake_post,
    )
    assert client.next_message(
        query="q",
        trace=[query_event("r", "q")],
        tools=_specs(),
        memory=[],
    ) == NapAnswer(text="Final answer.")


def test_http_error_uses_anthropic_error_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")

    def fake_post(
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]:
        return 400, json.dumps(
            {"type": "error", "error": {"type": "invalid_request_error", "message": "bad"}}
        ).encode()

    client = AnthropicMessagesModelClient(base_url="https://x", model="m", post_fn=fake_post)
    with pytest.raises(ModelInvocationError, match="bad"):
        client.next_message(
            query="q",
            trace=[query_event("r", "q")],
            tools=_specs(),
            memory=[],
        )

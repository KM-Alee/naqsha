"""Gemini generateContent adapter tests (mocked HTTP)."""

from __future__ import annotations

import json

import pytest

from naqsha.models.errors import ModelInvocationError
from naqsha.models.gemini import GeminiGenerateContentModelClient
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


def test_function_call_maps_to_nap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    def fake_post(
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]:
        assert ":generateContent" in url
        assert headers.get("x-goog-api-key") == "k"
        payload = json.loads(body.decode())
        assert payload["generationConfig"]["temperature"] == 0
        resp = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"functionCall": {"name": "clock", "args": {}, "id": "fc_1"}},
                        ]
                    }
                }
            ]
        }
        return 200, json.dumps(resp).encode()

    client = GeminiGenerateContentModelClient(
        base_url="https://generativelanguage.googleapis.com",
        model="gemini-test",
        post_fn=fake_post,
    )
    msg = client.next_message(
        query="q",
        trace=[query_event("r", "q")],
        tools=_specs(),
        memory=[],
    )
    assert msg == NapAction(calls=(ToolCall(id="fc_1", name="clock", arguments={}),))


def test_text_parts_map_to_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    def fake_post(
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]:
        resp = {"candidates": [{"content": {"parts": [{"text": " ok "}]}}]}
        return 200, json.dumps(resp).encode()

    client = GeminiGenerateContentModelClient(
        base_url="https://generativelanguage.googleapis.com",
        model="gemini-test",
        post_fn=fake_post,
    )
    assert client.next_message(
        query="q",
        trace=[query_event("r", "q")],
        tools=_specs(),
        memory=[],
    ) == NapAnswer(text="ok")


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = GeminiGenerateContentModelClient(
        base_url="https://generativelanguage.googleapis.com",
        model="m",
    )
    with pytest.raises(ModelInvocationError, match="GEMINI_API_KEY"):
        client.next_message(
            query="q",
            trace=[query_event("r", "q")],
            tools=_specs(),
            memory=[],
        )

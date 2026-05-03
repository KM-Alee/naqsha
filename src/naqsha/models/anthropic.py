"""Anthropic Claude Messages API (stdlib HTTP).

Docs: https://docs.anthropic.com/en/api/messages — ``tool_use`` / ``tool_result`` blocks.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from naqsha.memory.base import MemoryRecord
from naqsha.models.base import ModelClient
from naqsha.models.errors import ModelInvocationError
from naqsha.models.http_json import default_post, post_json
from naqsha.models.nap import NapMessage, NapValidationError, attach_span_context, parse_nap_message
from naqsha.models.trace_turns import trace_to_transcript, transcript_to_anthropic_messages
from naqsha.protocols.qaoa import TraceEvent
from naqsha.tools.base import ToolSpec
from naqsha.tracing.span import SpanContext

_PostFn = Callable[[str, dict[str, str], bytes, float], tuple[int, bytes]]


def _anthropic_tools(specs: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "input_schema": spec.parameters,
        }
        for spec in sorted(specs, key=lambda s: s.name)
    ]


def _content_blocks_to_nap(content: Any) -> NapMessage:
    if not isinstance(content, list):
        raise ModelInvocationError("Anthropic response content must be an array.")

    nap_calls: list[dict[str, Any]] = []
    text_parts: list[str] = []

    for block in content:
        if not isinstance(block, dict):
            raise ModelInvocationError("Anthropic content block must be an object.")
        btype = block.get("type")
        if btype == "tool_use":
            cid = block.get("id")
            name = block.get("name")
            inp = block.get("input")
            if not isinstance(cid, str) or not cid:
                raise ModelInvocationError("tool_use id must be a non-empty string.")
            if not isinstance(name, str) or not name:
                raise ModelInvocationError("tool_use name must be a non-empty string.")
            if inp is None:
                inp = {}
            if not isinstance(inp, dict):
                raise ModelInvocationError("tool_use input must be an object.")
            nap_calls.append({"id": cid, "name": name, "arguments": inp})
        elif btype == "text":
            t = block.get("text")
            if isinstance(t, str) and t.strip():
                text_parts.append(t.strip())

    if nap_calls:
        try:
            return parse_nap_message({"kind": "action", "calls": nap_calls})
        except NapValidationError as exc:
            raise ModelInvocationError(
                f"Anthropic tool_use blocks are not valid NAP: {exc}"
            ) from exc

    joined = "\n".join(text_parts).strip()
    if joined:
        try:
            return parse_nap_message({"kind": "answer", "text": joined})
        except NapValidationError as exc:
            raise ModelInvocationError(f"Anthropic text answer is not valid NAP: {exc}") from exc

    raise ModelInvocationError("Anthropic response has neither tool_use nor non-empty text.")


class AnthropicMessagesModelClient(ModelClient):
    """POST ``{base_url}/v1/messages``."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key_env: str = "ANTHROPIC_API_KEY",
        timeout_seconds: float = 120.0,
        max_tokens: int = 4096,
        anthropic_version: str = "2023-06-01",
        post_fn: _PostFn | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key_env = api_key_env
        self._timeout_seconds = timeout_seconds
        self._max_tokens = max_tokens
        self._anthropic_version = anthropic_version
        self._post_fn = post_fn

    def next_message(
        self,
        *,
        query: str,
        trace: list[TraceEvent],
        tools: list[ToolSpec],
        memory: list[MemoryRecord],
        span_context: SpanContext | None = None,
        instructions: str = "",
    ) -> NapMessage:
        api_key = os.environ.get(self._api_key_env, "").strip()
        if not api_key:
            raise ModelInvocationError(
                f"Environment variable {self._api_key_env!r} is not set or empty."
            )

        transcript = trace_to_transcript(
            query=query, trace=trace, memory=memory, instructions=instructions
        )
        system_text, anthropic_messages = transcript_to_anthropic_messages(transcript)

        url = f"{self._base_url}/v1/messages"
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": system_text,
            "messages": anthropic_messages,
            "tools": _anthropic_tools(tools),
            "temperature": 0,
        }

        wrapper = self._post_fn if self._post_fn is not None else default_post

        def _post(
            url_: str,
            headers: dict[str, str],
            body: bytes,
            timeout: float,
        ) -> tuple[int, bytes]:
            return wrapper(url_, headers, body, timeout)

        parsed = post_json(
            url,
            headers={
                "x-api-key": api_key,
                "anthropic-version": self._anthropic_version,
            },
            payload=payload,
            timeout_seconds=self._timeout_seconds,
            post_fn=_post,
            error_label="Anthropic Messages API",
        )

        msg_content = parsed.get("content")
        return attach_span_context(_content_blocks_to_nap(msg_content), span_context)

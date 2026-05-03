"""Ollama local ``/api/chat`` adapter (stdlib HTTP, OpenAI-style tool calling)."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from naqsha.memory.base import MemoryRecord
from naqsha.models.base import ModelClient
from naqsha.models.errors import ModelInvocationError
from naqsha.models.http_json import default_post, post_json
from naqsha.models.nap import NapMessage, attach_span_context
from naqsha.models.openai_compat import (
    _openai_message_to_nap,
    _tools_payload,
    trace_to_chat_messages,
)
from naqsha.protocols.qaoa import TraceEvent
from naqsha.tools.base import ToolSpec
from naqsha.tracing.span import SpanContext

_PostFn = Callable[[str, dict[str, str], bytes, float], tuple[int, bytes]]


class OllamaChatModelClient(ModelClient):
    """POST ``{base_url}/api/chat`` with tool definitions compatible with Ollama."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key_env: str | None = None,
        timeout_seconds: float = 120.0,
        post_fn: _PostFn | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key_env = api_key_env
        self._timeout_seconds = timeout_seconds
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
        headers: dict[str, str] = {}
        if self._api_key_env:
            api_key = os.environ.get(self._api_key_env, "").strip()
            if not api_key:
                raise ModelInvocationError(
                    f"Environment variable {self._api_key_env!r} is not set or empty."
                )
            headers["Authorization"] = f"Bearer {api_key}"

        messages = trace_to_chat_messages(
            query=query, trace=trace, memory=memory, instructions=instructions
        )
        url = f"{self._base_url}/api/chat"
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "tools": _tools_payload(tools),
            "stream": False,
            "options": {"temperature": 0},
        }
        wrapper = self._post_fn if self._post_fn is not None else default_post

        def _post(
            url_: str,
            hdrs: dict[str, str],
            body: bytes,
            timeout: float,
        ) -> tuple[int, bytes]:
            return wrapper(url_, hdrs, body, timeout)

        parsed = post_json(
            url,
            headers=headers,
            payload=payload,
            timeout_seconds=self._timeout_seconds,
            post_fn=_post,
            error_label="Ollama chat",
        )

        message = parsed.get("message")
        if not isinstance(message, dict):
            raise ModelInvocationError("Ollama response missing message object.")

        return attach_span_context(_openai_message_to_nap(message), span_context)

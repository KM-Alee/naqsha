"""OpenAI-compatible Chat Completions (stdlib HTTP).

Maps ``choices[0].message.tool_calls`` or text ``content`` to validated NAP messages.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from naqsha.memory.base import MemoryRecord
from naqsha.models.base import ModelClient
from naqsha.models.errors import ModelInvocationError
from naqsha.models.http_json import default_post, post_json
from naqsha.models.trace_turns import trace_to_transcript, transcript_to_openai_chat_messages
from naqsha.protocols.nap import NapMessage, NapValidationError, parse_nap_message
from naqsha.protocols.qaoa import TraceEvent
from naqsha.tools.base import ToolSpec

_PostFn = Callable[[str, dict[str, str], bytes, float], tuple[int, bytes]]


def trace_to_chat_messages(
    *,
    query: str,
    trace: list[TraceEvent],
    memory: list[MemoryRecord],
) -> list[dict[str, Any]]:
    """Rebuild OpenAI Chat Completions ``messages`` from QAOA trace + memory."""

    t = trace_to_transcript(query=query, trace=trace, memory=memory)
    return transcript_to_openai_chat_messages(t)


def _tools_payload(specs: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            },
        }
        for spec in sorted(specs, key=lambda s: s.name)
    ]


def _openai_message_to_nap(message: dict[str, Any]) -> NapMessage:
    tool_calls = message.get("tool_calls")
    content = message.get("content")

    if isinstance(tool_calls, list) and tool_calls:
        nap_calls: list[dict[str, Any]] = []
        for tc in tool_calls:
            if not isinstance(tc, dict):
                raise ModelInvocationError("tool_calls entry must be an object.")
            cid = tc.get("id")
            if not isinstance(cid, str) or not cid:
                raise ModelInvocationError("tool_call id must be a non-empty string.")
            fn = tc.get("function")
            if not isinstance(fn, dict):
                raise ModelInvocationError("tool_call.function must be an object.")
            name = fn.get("name")
            raw_args = fn.get("arguments")
            if not isinstance(name, str) or not name:
                raise ModelInvocationError("tool_call function name must be a non-empty string.")
            if isinstance(raw_args, str):
                raw_args = raw_args.strip()
                try:
                    arguments = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError as exc:
                    raise ModelInvocationError(
                        f"tool_call arguments are not valid JSON: {exc}"
                    ) from exc
            elif isinstance(raw_args, dict):
                arguments = raw_args
            elif raw_args is None:
                arguments = {}
            else:
                raise ModelInvocationError("tool_call arguments must be string or object.")
            if not isinstance(arguments, dict):
                raise ModelInvocationError("Parsed tool arguments must be an object.")
            nap_calls.append({"id": cid, "name": name, "arguments": arguments})
        try:
            return parse_nap_message({"kind": "action", "calls": nap_calls})
        except NapValidationError as exc:
            raise ModelInvocationError(f"Provider tool_calls are not valid NAP: {exc}") from exc

    if isinstance(content, str):
        text = content.strip()
        if text:
            try:
                return parse_nap_message({"kind": "answer", "text": text})
            except NapValidationError as exc:
                raise ModelInvocationError(f"Provider answer text is not valid NAP: {exc}") from exc

    raise ModelInvocationError(
        "Provider message has neither usable tool_calls nor a non-empty text answer."
    )


class OpenAiCompatModelClient(ModelClient):
    """POST ``{base_url}/chat/completions`` on an OpenAI-compatible server."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key_env: str = "OPENAI_API_KEY",
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
    ) -> NapMessage:
        api_key = os.environ.get(self._api_key_env, "").strip()
        if not api_key:
            raise ModelInvocationError(
                f"Environment variable {self._api_key_env!r} is not set or empty."
            )

        transcript = trace_to_transcript(query=query, trace=trace, memory=memory)
        messages = transcript_to_openai_chat_messages(transcript)
        url = f"{self._base_url}/chat/completions"
        payload = {
            "model": self._model,
            "messages": messages,
            "tools": _tools_payload(tools),
            "tool_choice": "auto",
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
            headers={"Authorization": f"Bearer {api_key}"},
            payload=payload,
            timeout_seconds=self._timeout_seconds,
            post_fn=_post,
            error_label="OpenAI-compatible chat completion",
        )

        choices = parsed.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ModelInvocationError("Provider response missing choices[0].")
        first = choices[0]
        if not isinstance(first, dict):
            raise ModelInvocationError("choices[0] must be an object.")
        message = first.get("message")
        if not isinstance(message, dict):
            raise ModelInvocationError("choices[0].message must be an object.")

        return _openai_message_to_nap(message)

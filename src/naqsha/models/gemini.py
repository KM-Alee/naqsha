"""Google Gemini ``generateContent`` (stdlib HTTP).

Uses ``functionDeclarations`` / ``functionCall`` / ``functionResponse`` per
https://ai.google.dev/gemini-api/docs/function-calling
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from naqsha.memory.base import MemoryRecord
from naqsha.models.base import ModelClient
from naqsha.models.errors import ModelInvocationError
from naqsha.models.http_json import default_post, post_json
from naqsha.models.trace_turns import trace_to_transcript, transcript_to_gemini_contents
from naqsha.protocols.nap import NapMessage, NapValidationError, parse_nap_message
from naqsha.protocols.qaoa import TraceEvent
from naqsha.tools.base import ToolSpec

_PostFn = Callable[[str, dict[str, str], bytes, float], tuple[int, bytes]]


def _gemini_declarations(specs: list[ToolSpec]) -> list[dict[str, Any]]:
    decls = []
    for spec in sorted(specs, key=lambda s: s.name):
        decls.append(
            {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            }
        )
    return decls


def _candidate_parts_to_nap(parts: Any) -> NapMessage:
    if not isinstance(parts, list):
        raise ModelInvocationError("Gemini candidate parts must be an array.")

    nap_calls: list[dict[str, Any]] = []
    text_chunks: list[str] = []

    for i, part in enumerate(parts):
        if not isinstance(part, dict):
            raise ModelInvocationError("Gemini part must be an object.")
        if "functionCall" in part:
            fc = part["functionCall"]
            if not isinstance(fc, dict):
                raise ModelInvocationError("functionCall must be an object.")
            name = fc.get("name")
            args = fc.get("args")
            cid = fc.get("id")
            if not isinstance(name, str) or not name:
                raise ModelInvocationError("functionCall.name must be a non-empty string.")
            if args is None:
                arguments: dict[str, Any] = {}
            elif isinstance(args, dict):
                arguments = args
            else:
                raise ModelInvocationError("functionCall.args must be an object when present.")
            call_id = cid if isinstance(cid, str) and cid else f"gemini-call-{i}-{name}"
            nap_calls.append({"id": call_id, "name": name, "arguments": arguments})
        if "text" in part:
            t = part.get("text")
            if isinstance(t, str) and t.strip():
                text_chunks.append(t.strip())

    if nap_calls:
        try:
            return parse_nap_message({"kind": "action", "calls": nap_calls})
        except NapValidationError as exc:
            raise ModelInvocationError(
                f"Gemini functionCall parts are not valid NAP: {exc}"
            ) from exc

    joined = "\n".join(text_chunks).strip()
    if joined:
        try:
            return parse_nap_message({"kind": "answer", "text": joined})
        except NapValidationError as exc:
            raise ModelInvocationError(f"Gemini text answer is not valid NAP: {exc}") from exc

    raise ModelInvocationError("Gemini response has neither functionCall nor non-empty text.")


class GeminiGenerateContentModelClient(ModelClient):
    """POST ``{base}/v1beta/models/{model}:generateContent``."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key_env: str = "GEMINI_API_KEY",
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
        system_instruction, contents = transcript_to_gemini_contents(transcript)

        url = f"{self._base_url}/v1beta/models/{self._model}:generateContent"
        payload: dict[str, Any] = {
            "systemInstruction": system_instruction,
            "contents": contents,
            "tools": [{"functionDeclarations": _gemini_declarations(tools)}],
            "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
            "generationConfig": {"temperature": 0},
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
            headers={"x-goog-api-key": api_key},
            payload=payload,
            timeout_seconds=self._timeout_seconds,
            post_fn=_post,
            error_label="Gemini generateContent",
        )

        candidates = parsed.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ModelInvocationError("Gemini response missing candidates[0].")
        cand0 = candidates[0]
        if not isinstance(cand0, dict):
            raise ModelInvocationError("candidates[0] must be an object.")
        inner = cand0.get("content")
        if not isinstance(inner, dict):
            raise ModelInvocationError("candidate.content must be an object.")
        parts = inner.get("parts")
        return _candidate_parts_to_nap(parts)

"""NAP V2 Action protocol (canonical definitions for Model Adapters and Core Runtime).

Validated NAP messages are the only model output the Core Runtime consumes. Thin
Adapters translate provider-native responses into these dataclasses. Optional
``span_context`` carries :class:`~naqsha.tracing.span.SpanContext` for propagation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal

from naqsha.tracing.span import SpanContext


class NapValidationError(ValueError):
    """Raised when a model message cannot become a valid NAP message."""


_NAP_CALL_ID_MAX_LEN = 256


def _validate_call_id(call_id: str) -> None:
    if len(call_id) > _NAP_CALL_ID_MAX_LEN:
        raise NapValidationError("Tool call id exceeds maximum length.")
    if call_id != call_id.strip():
        raise NapValidationError("Tool call id must not have leading or trailing whitespace.")
    if any(ch in call_id for ch in ("\x00", "\n", "\r")):
        raise NapValidationError("Tool call id contains forbidden characters.")


def _validate_arguments_object(arguments: dict[str, Any]) -> None:
    for key in arguments:
        if not isinstance(key, str):
            raise NapValidationError("Tool call arguments must use string keys only.")
        if not key:
            raise NapValidationError("Tool call arguments must not use empty property keys.")


def _parse_span_context_payload(raw: Any) -> SpanContext:
    if not isinstance(raw, dict):
        raise NapValidationError("span_context must be a JSON object.")
    allowed = {"trace_id", "span_id", "parent_span_id", "agent_id"}
    extra = set(raw) - allowed
    if extra:
        raise NapValidationError(f"Unexpected span_context fields: {sorted(extra)}.")
    trace_id = raw.get("trace_id")
    span_id = raw.get("span_id")
    agent_id = raw.get("agent_id")
    parent = raw.get("parent_span_id")
    if not isinstance(trace_id, str) or not trace_id:
        raise NapValidationError("span_context.trace_id must be a non-empty string.")
    if not isinstance(span_id, str) or not span_id:
        raise NapValidationError("span_context.span_id must be a non-empty string.")
    if not isinstance(agent_id, str) or not agent_id:
        raise NapValidationError("span_context.agent_id must be a non-empty string.")
    if parent is not None and not isinstance(parent, str):
        raise NapValidationError("span_context.parent_span_id must be a string or null.")
    return SpanContext(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent,
        agent_id=agent_id,
    )


def span_context_to_dict(ctx: SpanContext) -> dict[str, Any]:
    return {
        "trace_id": ctx.trace_id,
        "span_id": ctx.span_id,
        "parent_span_id": ctx.parent_span_id,
        "agent_id": ctx.agent_id,
    }


@dataclass(frozen=True)
class ToolCall:
    """A single requested tool call inside a NAP action."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class NapAction:
    """A model request to execute one or more tools."""

    calls: tuple[ToolCall, ...]
    kind: Literal["action"] = "action"
    span_context: SpanContext | None = None


@dataclass(frozen=True)
class NapAnswer:
    """A model final answer."""

    text: str
    kind: Literal["answer"] = "answer"
    span_context: SpanContext | None = None


NapMessage = NapAction | NapAnswer


def parse_nap_message(payload: dict[str, Any]) -> NapMessage:
    """Validate untrusted model output into a NAP message."""

    if not isinstance(payload, dict):
        raise NapValidationError("NAP message must be a JSON object.")

    kind = payload.get("kind")
    if not isinstance(kind, str):
        raise NapValidationError("NAP message kind must be a string.")

    has_span_key = "span_context" in payload
    span_raw = payload.get("span_context")
    span_ctx: SpanContext | None = None
    if span_raw is not None:
        span_ctx = _parse_span_context_payload(span_raw)

    if kind == "answer":
        base_keys = {"kind", "text"}
        if has_span_key:
            base_keys = base_keys | {"span_context"}
        unexpected = set(payload) - base_keys
        if unexpected:
            raise NapValidationError(f"Unexpected NAP fields: {sorted(unexpected)}")
        text = payload.get("text")
        if not isinstance(text, str) or not text:
            raise NapValidationError("NAP answer requires non-empty text.")
        return NapAnswer(text=text, span_context=span_ctx)

    if kind == "action":
        base_keys = {"kind", "calls"}
        if has_span_key:
            base_keys = base_keys | {"span_context"}
        unexpected = set(payload) - base_keys
        if unexpected:
            raise NapValidationError(f"Unexpected NAP fields: {sorted(unexpected)}")
        calls = payload.get("calls")
        if not isinstance(calls, list) or not calls:
            raise NapValidationError("NAP action requires one or more calls.")

        seen_ids: set[str] = set()
        parsed: list[ToolCall] = []
        for raw in calls:
            if not isinstance(raw, dict):
                raise NapValidationError("Each tool call must be an object.")
            if set(raw) - {"id", "name", "arguments"}:
                raise NapValidationError("Tool call contains unexpected fields.")
            call_id = raw.get("id")
            name = raw.get("name")
            arguments = raw.get("arguments")
            if not isinstance(call_id, str) or not call_id:
                raise NapValidationError("Tool call id must be a non-empty string.")
            _validate_call_id(call_id)
            if call_id in seen_ids:
                raise NapValidationError(f"Duplicate tool call id: {call_id}")
            if not isinstance(name, str) or not name:
                raise NapValidationError("Tool call name must be a non-empty string.")
            if not isinstance(arguments, dict):
                raise NapValidationError("Tool call arguments must be an object.")
            _validate_arguments_object(arguments)
            seen_ids.add(call_id)
            parsed.append(ToolCall(id=call_id, name=name, arguments=arguments))
        return NapAction(calls=tuple(parsed), span_context=span_ctx)

    raise NapValidationError("NAP message kind must be 'action' or 'answer'.")


def nap_to_dict(message: NapMessage) -> dict[str, Any]:
    """Serialize a NAP message to JSON-compatible data."""

    if isinstance(message, NapAnswer):
        d: dict[str, Any] = {"kind": "answer", "text": message.text}
        if message.span_context is not None:
            d["span_context"] = span_context_to_dict(message.span_context)
        return d
    d = {
        "kind": "action",
        "calls": [
            {"id": call.id, "name": call.name, "arguments": call.arguments}
            for call in message.calls
        ],
    }
    if message.span_context is not None:
        d["span_context"] = span_context_to_dict(message.span_context)
    return d


def attach_span_context(message: NapMessage, span_context: SpanContext | None) -> NapMessage:
    """Return a copy of ``message`` with ``span_context`` set.

    If ``span_context`` is None, returns ``message`` unchanged.
    """

    if span_context is None:
        return message
    return replace(message, span_context=span_context)

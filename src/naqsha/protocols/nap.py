"""NAP Action protocol.

The Core Runtime consumes only validated NAP messages. Provider adapters translate
provider-native responses into these dataclasses before runtime execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


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


@dataclass(frozen=True)
class NapAnswer:
    """A model final answer."""

    text: str
    kind: Literal["answer"] = "answer"


NapMessage = NapAction | NapAnswer


def parse_nap_message(payload: dict[str, Any]) -> NapMessage:
    """Validate untrusted model output into a NAP message."""

    if not isinstance(payload, dict):
        raise NapValidationError("NAP message must be a JSON object.")

    kind = payload.get("kind")
    if not isinstance(kind, str):
        raise NapValidationError("NAP message kind must be a string.")

    allowed_keys = {"kind", "calls"} if kind == "action" else {"kind", "text"}
    unexpected = set(payload) - allowed_keys
    if unexpected:
        raise NapValidationError(f"Unexpected NAP fields: {sorted(unexpected)}")

    if kind == "answer":
        text = payload.get("text")
        if not isinstance(text, str) or not text:
            raise NapValidationError("NAP answer requires non-empty text.")
        return NapAnswer(text=text)

    if kind == "action":
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
        return NapAction(calls=tuple(parsed))

    raise NapValidationError("NAP message kind must be 'action' or 'answer'.")


def nap_to_dict(message: NapMessage) -> dict[str, Any]:
    """Serialize a NAP message to JSON-compatible data."""

    if isinstance(message, NapAnswer):
        return {"kind": "answer", "text": message.text}
    return {
        "kind": "action",
        "calls": [
            {"id": call.id, "name": call.name, "arguments": call.arguments}
            for call in message.calls
        ],
    }

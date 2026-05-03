"""QAOA Trace event model.

Each persisted JSONL record includes ``schema_version`` so readers can evolve without
breaking older traces: unknown schema versions fail closed at load time; missing
``schema_version`` is treated as ``1`` for pre-versioned lines.

V1 keeps dataclass serialization rather than adding a third-party validation library;
call sites construct events through helpers and ``TraceEvent.from_dict`` enforces the
on-disk shape at replay time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import uuid4

TraceKind = Literal["query", "action", "observation", "answer", "failure"]

QAOA_TRACE_SCHEMA_VERSION = 2

_SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2})

_TRACE_TOP_LEVEL_KEYS = frozenset(
    {
        "event_id",
        "run_id",
        "kind",
        "created_at",
        "payload",
        "schema_version",
        # V2 fields
        "trace_id",
        "span_id",
        "parent_span_id",
        "agent_id",
    }
)


class TraceValidationError(ValueError):
    """Raised when a serialized QAOA trace record is structurally invalid."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TraceValidationError(f"{field_name} must be a string.")
    if not value:
        raise TraceValidationError(f"{field_name} must be non-empty.")
    return value


def _validate_payload_shape(kind: TraceKind, payload: dict[str, Any]) -> None:
    if kind == "query":
        if "query" not in payload or not isinstance(payload["query"], str):
            raise TraceValidationError("Query payload requires string 'query'.")
    elif kind == "action":
        if "action" not in payload or not isinstance(payload["action"], dict):
            raise TraceValidationError("Action payload requires object 'action'.")
        if "policy" not in payload or not isinstance(payload["policy"], list):
            raise TraceValidationError("Action payload requires array 'policy'.")
        if "scheduler" in payload:
            sched = payload["scheduler"]
            if not isinstance(sched, dict):
                raise TraceValidationError("Action scheduler metadata must be an object.")
            mode = sched.get("mode")
            if mode not in ("serial", "parallel"):
                raise TraceValidationError("Action scheduler.mode must be 'serial' or 'parallel'.")
            if "parallel_eligible" in sched and not isinstance(sched["parallel_eligible"], bool):
                raise TraceValidationError("Action scheduler.parallel_eligible must be a boolean.")
    elif kind == "observation":
        for key in ("call_id", "tool", "observation"):
            if key not in payload:
                raise TraceValidationError(f"Observation payload missing '{key}'.")
        if not isinstance(payload["call_id"], str) or not payload["call_id"]:
            raise TraceValidationError("Observation call_id must be a non-empty string.")
        if not isinstance(payload["tool"], str) or not payload["tool"]:
            raise TraceValidationError("Observation tool must be a non-empty string.")
        if not isinstance(payload["observation"], dict):
            raise TraceValidationError("Observation observation must be an object.")
    elif kind == "answer":
        if "answer" not in payload or not isinstance(payload["answer"], str):
            raise TraceValidationError("Answer payload requires string 'answer'.")
    elif kind == "failure":
        for key in ("code", "message"):
            if key not in payload or not isinstance(payload[key], str):
                raise TraceValidationError(f"Failure payload requires string '{key}'.")


@dataclass(frozen=True)
class TraceEvent:
    """A single persisted QAOA trace event."""

    kind: TraceKind
    run_id: str
    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now)
    schema_version: int = QAOA_TRACE_SCHEMA_VERSION
    # V2 hierarchical trace fields
    trace_id: str = ""
    span_id: str = ""
    parent_span_id: str | None = None
    agent_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "run_id": self.run_id,
            "kind": self.kind,
            "created_at": self.created_at,
            "payload": self.payload,
        }
        # Include V2 fields if schema version is 2
        if self.schema_version >= 2:
            result["trace_id"] = self.trace_id
            result["span_id"] = self.span_id
            result["parent_span_id"] = self.parent_span_id
            result["agent_id"] = self.agent_id
        return result

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TraceEvent:
        if not isinstance(payload, dict):
            raise TraceValidationError("Trace event must be a JSON object.")

        unknown = set(payload) - _TRACE_TOP_LEVEL_KEYS
        if unknown:
            raise TraceValidationError(f"Unexpected trace fields: {sorted(unknown)}")

        raw_version = payload.get("schema_version", 1)  # V1 default for backward compat
        if type(raw_version) is not int or raw_version not in _SUPPORTED_SCHEMA_VERSIONS:
            raise TraceValidationError(f"Unsupported QAOA trace schema_version: {raw_version!r}.")

        kind_raw = payload.get("kind")
        if kind_raw not in ("query", "action", "observation", "answer", "failure"):
            raise TraceValidationError("Invalid trace event kind.")
        kind = cast("TraceKind", kind_raw)

        event_id = _require_str(payload.get("event_id"), "event_id")
        run_id = _require_str(payload.get("run_id"), "run_id")
        created_at = _require_str(payload.get("created_at"), "created_at")

        inner = payload.get("payload")
        if not isinstance(inner, dict):
            raise TraceValidationError("Trace payload must be an object.")

        _validate_payload_shape(kind, inner)

        # V2 fields: read if present, generate defaults for V1 traces
        trace_id = payload.get("trace_id", "")
        span_id = payload.get("span_id", "")
        parent_span_id = payload.get("parent_span_id")
        agent_id = payload.get("agent_id", "")
        
        # For V1 traces without span_id, generate one to treat as root span
        if raw_version == 1 and not span_id:
            span_id = str(uuid4())
            trace_id = run_id  # Use run_id as trace_id for V1 traces

        return cls(
            schema_version=raw_version,
            event_id=event_id,
            run_id=run_id,
            kind=kind,
            created_at=created_at,
            payload=dict(inner),
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            agent_id=agent_id,
        )


def query_event(
    run_id: str,
    query: str,
    *,
    trace_id: str = "",
    span_id: str = "",
    parent_span_id: str | None = None,
    agent_id: str = "",
) -> TraceEvent:
    return TraceEvent(
        kind="query",
        run_id=run_id,
        payload={"query": query},
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        agent_id=agent_id,
    )


def action_event(
    run_id: str,
    action: dict[str, Any],
    policy: list[dict[str, Any]],
    *,
    scheduler: dict[str, Any] | None = None,
    trace_id: str = "",
    span_id: str = "",
    parent_span_id: str | None = None,
    agent_id: str = "",
) -> TraceEvent:
    body: dict[str, Any] = {"action": action, "policy": policy}
    if scheduler is not None:
        body["scheduler"] = scheduler
    return TraceEvent(
        kind="action",
        run_id=run_id,
        payload=body,
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        agent_id=agent_id,
    )


def observation_event(
    run_id: str,
    call_id: str,
    tool: str,
    observation: dict[str, Any],
    *,
    trace_id: str = "",
    span_id: str = "",
    parent_span_id: str | None = None,
    agent_id: str = "",
    tool_exec_ms: float | None = None,
) -> TraceEvent:
    payload: dict[str, Any] = {
        "call_id": call_id,
        "tool": tool,
        "observation": observation,
    }
    if tool_exec_ms is not None:
        payload["tool_exec_ms"] = tool_exec_ms
    return TraceEvent(
        kind="observation",
        run_id=run_id,
        payload=payload,
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        agent_id=agent_id,
    )


def answer_event(
    run_id: str,
    answer: str,
    *,
    trace_id: str = "",
    span_id: str = "",
    parent_span_id: str | None = None,
    agent_id: str = "",
) -> TraceEvent:
    return TraceEvent(
        kind="answer",
        run_id=run_id,
        payload={"answer": answer},
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        agent_id=agent_id,
    )


def failure_event(
    run_id: str,
    code: str,
    message: str,
    *,
    trace_id: str = "",
    span_id: str = "",
    parent_span_id: str | None = None,
    agent_id: str = "",
) -> TraceEvent:
    return TraceEvent(
        kind="failure",
        run_id=run_id,
        payload={"code": code, "message": message},
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        agent_id=agent_id,
    )

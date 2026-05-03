"""Deterministic replay helpers over QAOA Traces."""

from __future__ import annotations

from dataclasses import dataclass

from naqsha.protocols.nap import NapMessage, parse_nap_message
from naqsha.protocols.qaoa import TraceEvent
from naqsha.tools.base import ToolObservation
from naqsha.trace.base import TraceStore


class TraceReplayError(ValueError):
    """Invalid or incomplete trace for replay execution."""


@dataclass(frozen=True)
class ReplaySummary:
    run_id: str
    queries: list[str]
    observations: list[dict[str, object]]
    answer: str | None
    failures: list[dict[str, object]]


@dataclass(frozen=True)
class ReplayDiff:
    """Comparison between a reference trace and a freshly replayed run."""

    reference_run_id: str
    replay_run_id: str
    reference_answer: str | None
    replay_answer: str | None
    answer_matches: bool
    reference_tool_calls: list[dict[str, str]]
    replay_tool_calls: list[dict[str, str]]
    tool_calls_match: bool


def summarize_trace(trace_store: TraceStore, run_id: str) -> ReplaySummary:
    events: list[TraceEvent] = trace_store.load(run_id)
    answer = next(
        (event.payload["answer"] for event in reversed(events) if event.kind == "answer"),
        None,
    )
    return ReplaySummary(
        run_id=run_id,
        queries=[event.payload["query"] for event in events if event.kind == "query"],
        observations=[event.payload for event in events if event.kind == "observation"],
        answer=answer,
        failures=[event.payload for event in events if event.kind == "failure"],
    )


def first_query_from_trace(events: list[TraceEvent]) -> str:
    for event in events:
        if event.kind == "query":
            return event.payload["query"]
    raise TraceReplayError("Trace contains no query event.")


def nap_messages_from_trace(events: list[TraceEvent]) -> list[NapMessage]:
    """Ordered NapAction / NapAnswer sequence as originally modeled, from persisted events."""

    messages: list[NapMessage] = []
    for event in events:
        if event.kind == "action":
            messages.append(parse_nap_message(event.payload["action"]))
        elif event.kind == "answer":
            messages.append(parse_nap_message({"kind": "answer", "text": event.payload["answer"]}))
    if not messages:
        raise TraceReplayError("Trace contains no action or answer events to replay.")
    return messages


def observations_by_call_id(events: list[TraceEvent]) -> dict[str, ToolObservation]:
    """Map tool call id to observation payloads stored on disk (usually post-sanitizer)."""

    by_id: dict[str, ToolObservation] = {}
    for event in events:
        if event.kind != "observation":
            continue
        payload = event.payload
        call_id = payload["call_id"]
        if not isinstance(call_id, str) or not call_id:
            raise TraceReplayError("Observation event has invalid call_id.")
        obs = ToolObservation.from_trace_payload(payload["observation"])
        if call_id in by_id:
            raise TraceReplayError(f"Duplicate observation for call_id {call_id!r}.")
        by_id[call_id] = obs
    return by_id


def tool_calls_chronology(events: list[TraceEvent]) -> list[dict[str, str]]:
    """Per approved or denied call in trace order: tool name and call id (from action events)."""

    out: list[dict[str, str]] = []
    for event in events:
        if event.kind != "action":
            continue
        action = event.payload["action"]
        if not isinstance(action, dict) or action.get("kind") != "action":
            continue
        calls = action.get("calls")
        if not isinstance(calls, list):
            continue
        for raw in calls:
            if not isinstance(raw, dict):
                continue
            cid = raw.get("id")
            name = raw.get("name")
            if isinstance(cid, str) and isinstance(name, str) and cid and name:
                out.append({"call_id": cid, "tool": name})
    return out


def compare_replay(
    events_reference: list[TraceEvent], events_replay: list[TraceEvent]
) -> ReplayDiff:
    ref_id = events_reference[0].run_id if events_reference else ""
    rep_id = events_replay[0].run_id if events_replay else ""

    ref_answer = next(
        (e.payload["answer"] for e in reversed(events_reference) if e.kind == "answer"),
        None,
    )
    rep_answer = next(
        (e.payload["answer"] for e in reversed(events_replay) if e.kind == "answer"),
        None,
    )

    ref_tools = tool_calls_chronology(events_reference)
    rep_tools = tool_calls_chronology(events_replay)

    return ReplayDiff(
        reference_run_id=ref_id,
        replay_run_id=rep_id,
        reference_answer=ref_answer,
        replay_answer=rep_answer,
        answer_matches=ref_answer == rep_answer,
        reference_tool_calls=ref_tools,
        replay_tool_calls=rep_tools,
        tool_calls_match=ref_tools == rep_tools,
    )

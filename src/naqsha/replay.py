"""Deterministic replay helpers over QAOA Traces."""

from __future__ import annotations

from dataclasses import dataclass

from naqsha.protocols.qaoa import TraceEvent
from naqsha.trace.base import TraceStore


@dataclass(frozen=True)
class ReplaySummary:
    run_id: str
    queries: list[str]
    observations: list[dict[str, object]]
    answer: str | None
    failures: list[dict[str, object]]


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

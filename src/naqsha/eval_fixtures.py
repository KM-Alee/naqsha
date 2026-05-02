"""First-party eval fixtures: save expectations from a trace, check via replay."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from naqsha.protocols.qaoa import TraceEvent
from naqsha.replay import compare_replay, tool_calls_chronology

EVAL_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EvalFixture:
    """Golden snapshot for regression checks (answer + tool-call path)."""

    schema_version: int
    name: str
    reference_run_id: str
    expected_answer: str | None
    expected_tool_calls: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "reference_run_id": self.reference_run_id,
            "expected_answer": self.expected_answer,
            "expected_tool_calls": self.expected_tool_calls,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> EvalFixture:
        ver = int(data.get("schema_version", 1))
        if ver != EVAL_SCHEMA_VERSION:
            raise ValueError(f"Unsupported eval fixture schema_version {ver}.")
        name = str(data["name"])
        rid = str(data["reference_run_id"])
        ans = data.get("expected_answer")
        if ans is not None and not isinstance(ans, str):
            raise ValueError("expected_answer must be a string or null.")
        raw_calls = data.get("expected_tool_calls")
        if not isinstance(raw_calls, list):
            raise ValueError("expected_tool_calls must be a list.")
        calls: list[dict[str, str]] = []
        for item in raw_calls:
            if not isinstance(item, dict):
                raise ValueError("each expected_tool_calls item must be an object.")
            calls.append(
                {
                    "call_id": str(item["call_id"]),
                    "tool": str(item["tool"]),
                }
            )
        return EvalFixture(
            schema_version=ver,
            name=name,
            reference_run_id=rid,
            expected_answer=ans if isinstance(ans, str) else None,
            expected_tool_calls=calls,
        )


def build_fixture_from_trace(
    *,
    name: str,
    events: list[TraceEvent],
) -> EvalFixture:
    if not events:
        raise ValueError("Trace is empty.")
    run_id = events[0].run_id
    answer = next(
        (e.payload["answer"] for e in reversed(events) if e.kind == "answer"),
        None,
    )
    tools = tool_calls_chronology(events)
    return EvalFixture(
        schema_version=EVAL_SCHEMA_VERSION,
        name=name,
        reference_run_id=run_id,
        expected_answer=answer if isinstance(answer, str) else None,
        expected_tool_calls=tools,
    )


def save_fixture(path: Path, fixture: EvalFixture) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(fixture.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_fixture(path: Path) -> EvalFixture:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Eval fixture must be a JSON object.")
    return EvalFixture.from_dict(data)


def verify_trace_matches_fixture(events: list[TraceEvent], fixture: EvalFixture) -> list[str]:
    """Return list of human-readable mismatch messages (empty if ok)."""

    errors: list[str] = []
    if not events:
        errors.append("Trace is empty.")
        return errors
    if events[0].run_id != fixture.reference_run_id:
        errors.append(
            f"run_id mismatch: trace has {events[0].run_id!r}, "
            f"fixture expects {fixture.reference_run_id!r}."
        )
    answer = next(
        (e.payload["answer"] for e in reversed(events) if e.kind == "answer"),
        None,
    )
    if answer != fixture.expected_answer:
        errors.append(
            f"answer mismatch vs fixture: got {answer!r}, expected {fixture.expected_answer!r}."
        )
    tools = tool_calls_chronology(events)
    if tools != fixture.expected_tool_calls:
        errors.append(
            "tool path mismatch vs fixture: "
            f"got {tools!r}, expected {fixture.expected_tool_calls!r}."
        )
    return errors


def eval_check_result_dict(
    *,
    fixture: EvalFixture,
    reference_events: list[TraceEvent],
    replay_events: list[TraceEvent],
    trace_ok: bool,
) -> dict[str, Any]:
    replay_diff = compare_replay(reference_events, replay_events)
    return {
        "fixture_name": fixture.name,
        "reference_run_id": fixture.reference_run_id,
        "trace_matches_fixture": trace_ok,
        "replay_answer_matches_reference": replay_diff.answer_matches,
        "replay_tool_calls_match_reference": replay_diff.tool_calls_match,
        "passed": trace_ok and replay_diff.answer_matches and replay_diff.tool_calls_match,
    }

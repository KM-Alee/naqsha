"""Deterministic reflection candidate text from an evaluated QAOA trace."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from naqsha.protocols.qaoa import TraceEvent
from naqsha.reflection.reliability_gate import ReliabilityGateResult
from naqsha.replay import tool_calls_chronology


def build_candidate_markdown(events: list[TraceEvent], *, reliability_gate_passed: bool) -> str:
    if not events:
        return "# Reflection candidate\n\n(empty trace)\n"

    run_id = events[0].run_id
    lines: list[str] = [
        f"# Reflection candidate for run `{run_id}`",
        "",
        f"- generated_at: `{datetime.now(tz=UTC).isoformat()}`",
        f"- reliability_gate_passed: `{reliability_gate_passed}`",
        f"- ready_for_human_review: `{reliability_gate_passed}`",
        "",
        "## Trace outcomes",
        "",
    ]

    failures = [e for e in events if e.kind == "failure"]
    answer = next((e.payload["answer"] for e in reversed(events) if e.kind == "answer"), None)
    if failures:
        lines.append("Failure events:")
        for f in failures:
            code = f.payload.get("code", "?")
            msg = f.payload.get("message", "")
            lines.append(f"- `{code}`: {msg}")
        lines.append("")
    else:
        lines.append("No failure events recorded.")
        lines.append("")

    if answer is not None:
        lines.extend(["## Final answer", "", answer, ""])
    else:
        lines.extend(["## Final answer", "", "(none)", ""])

    chron = tool_calls_chronology(events)
    lines.extend(["## Tool call path (chronology)", ""])
    for row in chron:
        lines.append(f"- `{row['tool']}` call_id `{row['call_id']}`")
    if not chron:
        lines.append("(no tool calls in trace actions)")
    lines.append("")

    lines.extend(
        [
            "## Guidance (untrusted; for humans only)",
            "",
            "This file summarizes observable trace facts. It does not authorize runtime, "
            "policy, or approval changes.",
            "",
            "- If failures reference budgets or policy denials, inspect the trace and "
            "red-team fixtures before changing Tool Policy.",
            "- Prefer targeted test updates over widening approvals or bypassing gates.",
            "",
        ]
    )
    return "\n".join(lines)


def build_meta_json(
    events: list[TraceEvent],
    *,
    reliability_gate_passed: bool,
    gate_result: ReliabilityGateResult | None,
) -> str:
    run_id = events[0].run_id if events else ""
    payload: dict[str, object] = {
        "run_id": run_id,
        "reliability_gate_passed": reliability_gate_passed,
        "ready_for_human_review": reliability_gate_passed,
    }
    if gate_result is not None:
        payload["reliability_gate"] = {
            "passed": gate_result.passed,
            "returncode": gate_result.returncode,
            "command": list(gate_result.command),
        }
    return json.dumps(payload, indent=2, sort_keys=True)

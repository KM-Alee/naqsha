"""NAQSHA CLI."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from naqsha.approvals import ApprovalGate, InteractiveApprovalGate, StaticApprovalGate
from naqsha.memory.inmemory import InMemoryMemoryPort
from naqsha.memory.simplemem_cross import SimpleMemCrossMemoryPort
from naqsha.models.factory import model_client_from_profile
from naqsha.models.trace_replay import TraceReplayExhausted, TraceReplayModelClient
from naqsha.policy import ToolPolicy
from naqsha.profiles import (
    ProfileValidationError,
    RunProfile,
    describe_profile_dict,
    load_run_profile,
)
from naqsha.protocols.qaoa import TraceEvent
from naqsha.replay import (
    TraceReplayError,
    compare_replay,
    first_query_from_trace,
    nap_messages_from_trace,
    observations_by_call_id,
    summarize_trace,
)
from naqsha.runtime import CoreRuntime, RuntimeConfig
from naqsha.sanitizer import ObservationSanitizer
from naqsha.scheduler import ReplayObservationMissing, ToolScheduler
from naqsha.tools.base import RiskTier, Tool
from naqsha.tools.starter import starter_tools
from naqsha.trace.jsonl import JsonlTraceStore


def _tool_policy(profile: RunProfile, tools: dict[str, Tool]) -> ToolPolicy:
    if profile.allowed_tool_names is None:
        allowed = frozenset(tools)
    else:
        allowed = profile.allowed_tool_names
        missing = allowed - frozenset(tools)
        if missing:
            raise ProfileValidationError(
                f"allowed_tools contains names not loaded from Starter Tool Set: "
                f"{sorted(missing)}."
            )
    return ToolPolicy(
        allowed_tools=allowed,
        approval_required_tiers=profile.approval_required_tiers,
    )


def build_runtime(profile: RunProfile, *, approve_prompt: bool = False) -> CoreRuntime:
    tools = starter_tools(profile.tool_root)
    policy = _tool_policy(profile, tools)

    model = model_client_from_profile(profile)

    memory = None
    if profile.memory_adapter == "inmemory":
        memory = InMemoryMemoryPort()
    elif profile.memory_adapter == "simplemem_cross":
        memory = SimpleMemCrossMemoryPort(
            project=profile.memory_cross_project,
            database_path=profile.memory_cross_database,
        )

    if profile.auto_approve:
        gate: ApprovalGate = StaticApprovalGate(approved=True)
    elif approve_prompt:
        gate = InteractiveApprovalGate()
    else:
        gate = StaticApprovalGate(approved=False)

    return CoreRuntime(
        RuntimeConfig(
            model=model,
            tools=tools,
            trace_store=JsonlTraceStore(profile.trace_dir),
            policy=policy,
            budgets=profile.budgets,
            approval_gate=gate,
            sanitizer=ObservationSanitizer(max_chars=profile.sanitizer_max_chars),
            memory=memory,
            memory_token_budget=profile.memory_token_budget,
        )
    )


def build_trace_replay_runtime(
    profile: RunProfile,
    reference_events: list[TraceEvent],
    *,
    approve_prompt: bool = False,
) -> CoreRuntime:
    """Same wiring as ``build_runtime`` with trace-scripted model and recorded tools."""

    tools = starter_tools(profile.tool_root)
    policy = _tool_policy(profile, tools)

    memory = None
    if profile.memory_adapter == "inmemory":
        memory = InMemoryMemoryPort()
    elif profile.memory_adapter == "simplemem_cross":
        memory = SimpleMemCrossMemoryPort(
            project=profile.memory_cross_project,
            database_path=profile.memory_cross_database,
        )

    if profile.auto_approve:
        gate: ApprovalGate = StaticApprovalGate(approved=True)
    elif approve_prompt:
        gate = InteractiveApprovalGate()
    else:
        gate = StaticApprovalGate(approved=False)

    messages = nap_messages_from_trace(reference_events)
    recorded = observations_by_call_id(reference_events)

    return CoreRuntime(
        RuntimeConfig(
            model=TraceReplayModelClient(messages),
            tools=tools,
            trace_store=JsonlTraceStore(profile.trace_dir),
            policy=policy,
            budgets=profile.budgets,
            approval_gate=gate,
            sanitizer=ObservationSanitizer(max_chars=profile.sanitizer_max_chars),
            scheduler=ToolScheduler(recorded_observations=recorded),
            memory=memory,
            memory_token_budget=profile.memory_token_budget,
        )
    )


def inspect_policy_payload(profile: RunProfile) -> dict[str, Any]:
    tools_obj = starter_tools(profile.tool_root)
    policy = _tool_policy(profile, tools_obj)

    tools_meta: list[dict[str, Any]] = []
    for name in sorted(policy.allowed_tools):
        tool = tools_obj[name]
        needs = tool.spec.risk_tier in policy.approval_required_tiers
        tools_meta.append(
            {
                "name": name,
                "risk_tier": tool.spec.risk_tier.value,
                "tier_triggers_policy_approval": needs,
                "effective_with_static_gate": (
                    "allow"
                    if not needs or profile.auto_approve
                    else "denied_without_approval"
                ),
            }
        )

    unknown_starter = frozenset(tools_obj) - policy.allowed_tools
    return {
        "resolved_profile": describe_profile_dict(profile),
        "policy": {
            "allowed_tools": sorted(policy.allowed_tools),
            "approval_required_risk_tiers": sorted(t.value for t in policy.approval_required_tiers),
            "starter_tools_excluded_from_allowlist": sorted(unknown_starter),
            "approval_gate_mode": (
                "auto_approve_true" if profile.auto_approve else "auto_approve_false"
            ),
        },
        "tools": tools_meta,
        "risk_tiers_reference": sorted(t.value for t in RiskTier),
    }


def _add_profile_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile",
        metavar="PATH_OR_NAME",
        default="local-fake",
        help=(
            "Run Profile: path to a .json/.toml file, a bundled profile name "
            "(for example local-fake), or a file under profiles/ or examples/profiles/."
        ),
    )
    parser.add_argument(
        "--trace-dir",
        type=Path,
        default=None,
        help="Override trace_dir from the profile.",
    )
    parser.add_argument(
        "--tool-root",
        type=Path,
        default=None,
        help="Override tool_root from the profile.",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Override auto_approve to true so high-risk tools can execute locally.",
    )


def _apply_profile_overrides(profile: RunProfile, args: argparse.Namespace) -> RunProfile:
    out = profile
    if args.trace_dir is not None:
        out = replace(out, trace_dir=args.trace_dir.expanduser().resolve())
    if args.tool_root is not None:
        out = replace(out, tool_root=args.tool_root.expanduser().resolve())
    if args.auto_approve:
        out = replace(out, auto_approve=True)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="naqsha")
    subcommands = parser.add_subparsers(dest="command", required=True)

    run_parser = subcommands.add_parser("run", help="Execute a query with Core Runtime.")
    _add_profile_arguments(run_parser)
    run_parser.add_argument(
        "--approve-prompt",
        action="store_true",
        help=(
            "Prompt on stdin for each tool that requires approval. "
            "Ignored when auto_approve is true (profile or --auto-approve)."
        ),
    )
    run_parser.add_argument("query")

    replay_parser = subcommands.add_parser(
        "replay",
        help="Inspect a QAOA Trace, or re-execute it using stored observations (no live tools).",
    )
    _add_profile_arguments(replay_parser)
    replay_parser.add_argument(
        "--re-execute",
        action="store_true",
        help=(
            "Run the Core Runtime again with the same scripted model turns and tool observations "
            "from this trace (approved calls do not invoke real tools)."
        ),
    )
    replay_parser.add_argument(
        "--approve-prompt",
        action="store_true",
        help=(
            "When used with --re-execute, prompt on stdin for each approval-gated tool call. "
            "Ignored when auto_approve is true."
        ),
    )
    replay_parser.add_argument(
        "--human",
        action="store_true",
        help="Print a short text summary instead of JSON (summary mode only).",
    )
    replay_parser.add_argument("run_id")

    inspect_parser = subcommands.add_parser(
        "inspect-policy",
        help="Print resolved Run Profile Tool Policy snapshot (JSON).",
    )
    _add_profile_arguments(inspect_parser)

    args = parser.parse_args(argv)

    try:
        profile = load_run_profile(args.profile)
        profile = _apply_profile_overrides(profile, args)

        if args.command == "inspect-policy":
            print(json.dumps(inspect_policy_payload(profile), indent=2, sort_keys=True))
            return 0

        if args.command == "replay":
            trace_store = JsonlTraceStore(profile.trace_dir)
            if args.re_execute:
                reference = trace_store.load(args.run_id)
                if not reference:
                    print(
                        f"{parser.prog}: no trace file for run id {args.run_id!r} "
                        f"under {profile.trace_dir}.",
                        file=sys.stderr,
                    )
                    return 2
                try:
                    query = first_query_from_trace(reference)
                    runtime = build_trace_replay_runtime(
                        profile,
                        reference,
                        approve_prompt=args.approve_prompt,
                    )
                    result = runtime.run(query)
                except (TraceReplayError, TraceReplayExhausted, ReplayObservationMissing) as exc:
                    print(f"{parser.prog}: replay error: {exc}", file=sys.stderr)
                    return 2
                replay_events = trace_store.load(result.run_id)
                diff = compare_replay(reference, replay_events)
                print(
                    json.dumps(
                        {
                            "failed": result.failed,
                            "failure_code": result.failure_code,
                            "reference_run_id": args.run_id,
                            "replay_run_id": result.run_id,
                            "replay_answer": result.answer,
                            "answer_matches_reference": diff.answer_matches,
                            "tool_calls_match_reference": diff.tool_calls_match,
                            "reference_tool_calls": diff.reference_tool_calls,
                            "replay_tool_calls": diff.replay_tool_calls,
                            "reference_answer": diff.reference_answer,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return (
                    1
                    if result.failed
                    or not diff.answer_matches
                    or not diff.tool_calls_match
                    else 0
                )

            summary = summarize_trace(trace_store, args.run_id)
            if args.human:
                fail_n = len(summary.failures)
                print(f"run_id: {summary.run_id}")
                print(f"queries: {', '.join(summary.queries) or '(none)'}")
                print(f"observations: {len(summary.observations)}")
                if summary.answer is not None:
                    print(f"answer: {summary.answer}")
                else:
                    print("answer: (none)")
                print(f"failures: {fail_n}")
                for f in summary.failures:
                    print(f"  - {f.get('code', '?')}: {f.get('message', '')}")
                return 0
            print(json.dumps(summary.__dict__, default=str, sort_keys=True))
            return 0

        if args.command == "run":
            runtime = build_runtime(profile, approve_prompt=args.approve_prompt)
            result = runtime.run(args.query)
            print(
                json.dumps(
                    {"run_id": result.run_id, "answer": result.answer, "failed": result.failed},
                    sort_keys=True,
                )
            )
            return 1 if result.failed else 0

    except ProfileValidationError as exc:
        print(f"{parser.prog}: profile error: {exc}", file=sys.stderr)
        return 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""NAQSHA CLI and Agent Workbench."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from naqsha.core.event_bus import RuntimeEventBus
from naqsha.eval_fixtures import build_fixture_from_trace as build_eval_fixture
from naqsha.eval_fixtures import save_fixture
from naqsha.models.trace_replay import TraceReplayExhausted
from naqsha.profiles import ProfileValidationError, load_run_profile
from naqsha.project import evals_dir, init_agent_project
from naqsha.reflection.loop import SimpleReflectionLoop
from naqsha.reflection.rollback import AutomatedRollbackManager
from naqsha.replay import (
    TraceReplayError,
    compare_replay,
    first_query_from_trace,
    summarize_trace,
)
from naqsha.scheduler import ReplayObservationMissing
from naqsha.trace.jsonl import JsonlTraceStore
from naqsha.trace_scan import latest_run_id
from naqsha.wiring import (
    build_runtime,
    build_trace_replay_runtime,
    inspect_policy_payload,
)
from naqsha.workbench import AgentWorkbench, RuntimeBusReflectionSink


def _interactive_tui_enabled() -> bool:
    try:
        from naqsha.tui.app import cli_should_use_tui, tui_available
    except ImportError:
        return False
    return bool(tui_available() and cli_should_use_tui())


def _version_string() -> str:
    try:
        from importlib.metadata import version

        return version("naqsha")
    except Exception:
        return "0.0.0"


def _add_profile_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile",
        metavar="PATH_OR_NAME",
        default="local-fake",
        help=(
            "Run Profile: path to a .json/.toml file, a bundled profile name "
            "(for example local-fake), `.naqsha/profiles/` short names after `naqsha init`, "
            "or profiles/ / examples/profiles/ in the working directory."
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


def _apply_profile_overrides(profile: Any, args: argparse.Namespace) -> Any:
    out = profile
    if args.trace_dir is not None:
        out = replace(out, trace_dir=args.trace_dir.expanduser().resolve())
    if args.tool_root is not None:
        out = replace(out, tool_root=args.tool_root.expanduser().resolve())
    if args.auto_approve:
        out = replace(out, auto_approve=True)
    return out


def _resolve_run_id(args: argparse.Namespace, trace_dir: Path) -> str:
    if getattr(args, "latest", False):
        rid = latest_run_id(trace_dir)
        if not rid:
            raise ValueError(f"No traces under {trace_dir}.")
        return rid
    rid = getattr(args, "run_id", None)
    if not rid:
        raise ValueError("run_id is required unless --latest is set.")
    return rid


def _do_reflect(
    prog: str,
    profile: Any,
    run_id: str,
    workspace_base: Path | None,
) -> int:
    trace_store = JsonlTraceStore(profile.trace_dir)
    events = trace_store.load(run_id)
    if not events:
        print(
            f"{prog}: no trace file for run id {run_id!r} under {profile.trace_dir}.",
            file=sys.stderr,
        )
        return 2
    base = workspace_base
    if base is None:
        base = Path.cwd() / ".naqsha" / "reflection-workspaces"
    loop = SimpleReflectionLoop(
        workspace_parent=base.expanduser().resolve(),
        team_workspace=Path.cwd().resolve(),
        patch_event_sink=RuntimeBusReflectionSink(RuntimeEventBus()),
    )
    patch = loop.propose_patch(events)
    if patch is None:
        print(f"{prog}: reflection failed (empty trace).", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "workspace": str(patch.workspace),
                "summary": patch.summary,
                "reliability_gate_passed": patch.reliability_gate_passed,
                "ready_for_human_review": patch.ready_for_human_review,
                "auto_merged": patch.auto_merged,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="naqsha",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Agent Workbench quick path: init → run → replay RUN_ID → eval save → "
            "eval check → reflect|improve RUN_ID. "
            "Traces default to .naqsha/traces when using workbench init."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_version_string()}",
    )
    subcommands = parser.add_subparsers(dest="command", required=False)

    init_parser = subcommands.add_parser(
        "init",
        help="Create .naqsha/ Agent Workbench layout and a default profile.",
    )
    init_parser.add_argument(
        "--profile-name",
        default="workbench",
        help="Name for ``.naqsha/profiles/<name>.json`` (default: workbench).",
    )

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
    run_parser.add_argument(
        "--human",
        action="store_true",
        help="Print answer as plain text instead of JSON.",
    )
    run_parser.add_argument(
        "--no-hint",
        action="store_true",
        help="Do not print a replay hint to stderr after a successful run.",
    )
    run_parser.add_argument("query")

    replay_parser = subcommands.add_parser(
        "replay",
        help="Inspect a QAOA Trace, or re-execute it using stored observations (no live tools).",
    )
    _add_profile_arguments(replay_parser)
    replay_parser.add_argument(
        "--latest",
        action="store_true",
        help="Use the most recently modified trace in trace_dir instead of a run_id.",
    )
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
    replay_parser.add_argument("run_id", nargs="?", default=None)

    inspect_parser = subcommands.add_parser(
        "inspect-policy",
        help="Print resolved Run Profile Tool Policy snapshot (JSON).",
    )
    _add_profile_arguments(inspect_parser)

    profile_parser = subcommands.add_parser(
        "profile",
        help="Profile commands (alias for parts of inspect-policy).",
    )
    profile_sub = profile_parser.add_subparsers(dest="profile_cmd", required=True)
    profile_show = profile_sub.add_parser(
        "show",
        help="Same as inspect-policy: resolved profile and Tool Policy (JSON).",
    )
    _add_profile_arguments(profile_show)

    trace_parser = subcommands.add_parser("trace", help="Trace inspection commands.")
    trace_sub = trace_parser.add_subparsers(dest="trace_cmd", required=True)
    trace_inspect = trace_sub.add_parser(
        "inspect",
        help="Summarize a QAOA Trace (same as replay without --re-execute).",
    )
    _add_profile_arguments(trace_inspect)
    trace_inspect.add_argument(
        "--latest",
        action="store_true",
        help="Use the most recent trace in trace_dir.",
    )
    trace_inspect.add_argument("run_id", nargs="?", default=None)
    trace_inspect.add_argument(
        "--human",
        action="store_true",
        help="Print a short text summary instead of JSON.",
    )

    tools_parser = subcommands.add_parser("tools", help="Tool listing.")
    tools_sub = tools_parser.add_subparsers(dest="tools_cmd", required=True)
    tools_list = tools_sub.add_parser(
        "list",
        help="List allowed tools and risk metadata for the resolved profile (JSON).",
    )
    _add_profile_arguments(tools_list)

    eval_parser = subcommands.add_parser("eval", help="Regression expectations from traces.")
    eval_sub = eval_parser.add_subparsers(dest="eval_cmd", required=True)
    eval_save = eval_sub.add_parser(
        "save",
        help="Save expected answer + tool path from a trace into .naqsha/evals/<name>.json.",
    )
    _add_profile_arguments(eval_save)
    eval_save.add_argument("run_id")
    eval_save.add_argument(
        "name",
        help="Fixture name (filename without .json under .naqsha/evals/).",
    )
    eval_save.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Override output path (default: .naqsha/evals/<name>.json).",
    )

    eval_check = eval_sub.add_parser(
        "check",
        help="Verify trace matches a saved fixture, then re-execute and compare.",
    )
    _add_profile_arguments(eval_check)
    eval_check.add_argument("run_id")
    eval_check.add_argument(
        "--name",
        dest="fixture_name",
        required=True,
        help="Fixture name (loads .naqsha/evals/<name>.json).",
    )
    eval_check.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="Explicit path to fixture JSON (overrides --name).",
    )
    eval_check.add_argument(
        "--approve-prompt",
        action="store_true",
        help="Prompt for approvals during re-execute replay (same as replay --re-execute).",
    )

    reflect_parser = subcommands.add_parser(
        "reflect",
        help=(
            "Build an isolated Reflection Patch from a QAOA trace: run the Reliability Gate "
            "and write candidate artifacts for human review."
        ),
    )
    _add_profile_arguments(reflect_parser)
    reflect_parser.add_argument(
        "--workspace-base",
        type=Path,
        default=None,
        help=(
            "Directory in which a unique patch workspace is created "
            "(default: .naqsha/reflection-workspaces under the current working directory)."
        ),
    )
    reflect_parser.add_argument("run_id")

    improve_parser = subcommands.add_parser(
        "improve",
        help="Same as reflect: reviewed self-improvement patch workspace (+ IMPROVEMENT_NOTES.md).",
    )
    _add_profile_arguments(improve_parser)
    improve_parser.add_argument(
        "--workspace-base",
        type=Path,
        default=None,
        help="Same as reflect --workspace-base.",
    )
    improve_parser.add_argument("run_id")

    args = parser.parse_args(argv)

    if args.command is None:
        project = Path.cwd().resolve()
        if (project / "naqsha.toml").is_file():
            if _interactive_tui_enabled():
                from naqsha.tui.command_center import run_command_center

                run_command_center(cwd=project)
                return 0
            print(
                f"{parser.prog}: found naqsha.toml but interactive TUI is disabled "
                "(install the [tui] extra and ensure stdin/stdout are TTYs; "
                "unset NAQSHA_NO_TUI if set).",
                file=sys.stderr,
            )
            return 2
        print(
            f"{parser.prog}: no subcommand given and no naqsha.toml in {project}. "
            "Run `naqsha init` to create a Team Workspace, then `naqsha --help` for commands.",
            file=sys.stderr,
        )
        return 2

    try:
        if args.command == "init":
            if _interactive_tui_enabled():
                from naqsha.tui.wizard.init import run_init_wizard

                toml_path = run_init_wizard(
                    cwd=Path.cwd(), profile_name=args.profile_name
                )
                print(
                    json.dumps(
                        {
                            "initialized": True,
                            "naqsha_toml": str(toml_path),
                            "message": (
                                "Team Workspace written. "
                                "Run: naqsha run --profile <profile> \"query\" "
                                "(see .naqsha/profiles/)"
                            ),
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 0
            path = init_agent_project(profile_name=args.profile_name)
            print(
                json.dumps(
                    {
                        "initialized": True,
                        "profile": str(path),
                        "message": f'Run: naqsha run --profile {path.stem} "your query"',
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        profile = load_run_profile(args.profile)
        profile = _apply_profile_overrides(profile, args)

        if args.command == "inspect-policy" or (
            args.command == "profile" and args.profile_cmd == "show"
        ):
            print(json.dumps(inspect_policy_payload(profile), indent=2, sort_keys=True))
            return 0

        if args.command == "tools" and args.tools_cmd == "list":
            payload = inspect_policy_payload(profile)
            print(json.dumps(payload["tools"], indent=2, sort_keys=True))
            return 0

        if args.command == "eval" and args.eval_cmd == "save":
            wb = AgentWorkbench(profile)
            store = wb.trace_store()
            events = store.load(args.run_id)
            if not events:
                print(
                    f"{parser.prog}: no trace for run_id {args.run_id!r} "
                    f"under {profile.trace_dir}.",
                    file=sys.stderr,
                )
                return 2
            fix = build_eval_fixture(name=args.name, events=events)
            out = args.output
            if out is None:
                out = evals_dir() / f"{args.name}.json"
            save_fixture(out, fix)
            payload = {"saved": str(out), "fixture": fix.to_dict()}
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        if args.command == "eval" and args.eval_cmd == "check":
            wb = AgentWorkbench(profile)
            fpath = args.fixture
            if fpath is None:
                fpath = evals_dir() / f"{args.fixture_name}.json"
            if not fpath.is_file():
                print(f"{parser.prog}: fixture not found: {fpath}", file=sys.stderr)
                return 2
            result = wb.check_eval_fixture(
                args.run_id,
                fpath,
                approve_prompt=args.approve_prompt,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result.get("passed") else 1

        if args.command in ("reflect", "improve"):
            return _do_reflect(
                parser.prog,
                profile,
                args.run_id,
                getattr(args, "workspace_base", None),
            )

        if args.command == "trace" and args.trace_cmd == "inspect":
            trace_store = JsonlTraceStore(profile.trace_dir)
            try:
                run_id = _resolve_run_id(args, profile.trace_dir)
            except ValueError as exc:
                print(f"{parser.prog}: {exc}", file=sys.stderr)
                return 2
            summary = summarize_trace(trace_store, run_id)
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

        if args.command == "replay":
            trace_store = JsonlTraceStore(profile.trace_dir)
            try:
                run_id = _resolve_run_id(args, profile.trace_dir)
            except ValueError as exc:
                print(f"{parser.prog}: {exc}", file=sys.stderr)
                return 2

            if args.re_execute:
                reference = trace_store.load(run_id)
                if not reference:
                    print(
                        f"{parser.prog}: no trace file for run id {run_id!r} "
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
                            "reference_run_id": run_id,
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

            summary = summarize_trace(trace_store, run_id)
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
            mgr = AutomatedRollbackManager()
            bus = RuntimeEventBus()
            patch_sink = RuntimeBusReflectionSink(bus)

            def _boot_health() -> bool:
                try:
                    probe_rt = build_runtime(profile, approve_prompt=args.approve_prompt)
                    probe = probe_rt.run("__naqsha_boot_probe__")
                    return not probe.failed
                except Exception:
                    return False

            mgr.verify_boot_if_pending(
                Path.cwd(),
                health_check=_boot_health,
                event_sink=patch_sink,
            )
            if _interactive_tui_enabled():
                from naqsha.tui.app import build_workbench_app

                runtime = build_runtime(
                    profile, approve_prompt=args.approve_prompt, event_bus=bus
                )
                app = build_workbench_app(runtime=runtime, query=args.query)
                app.run()
                result = app.last_result
                if result is None:
                    return 130
                if args.human:
                    if result.answer is not None:
                        print(result.answer)
                    else:
                        print("(no answer)", file=sys.stderr)
                else:
                    print(
                        json.dumps(
                            {
                                "run_id": result.run_id,
                                "answer": result.answer,
                                "failed": result.failed,
                            },
                            sort_keys=True,
                        )
                    )
                if not args.no_hint and not result.failed:
                    hint = (
                        f"{parser.prog}: hint: naqsha replay --profile "
                        f"{args.profile!r} {result.run_id}"
                    )
                    print(hint, file=sys.stderr)
                return 1 if result.failed else 0

            runtime = build_runtime(profile, approve_prompt=args.approve_prompt)
            result = runtime.run(args.query)
            if args.human:
                if result.answer is not None:
                    print(result.answer)
                else:
                    print("(no answer)", file=sys.stderr)
            else:
                print(
                    json.dumps(
                        {
                            "run_id": result.run_id,
                            "answer": result.answer,
                            "failed": result.failed,
                        },
                        sort_keys=True,
                    )
                )
            if not args.no_hint and not result.failed:
                hint = (
                    f"{parser.prog}: hint: naqsha replay --profile "
                    f"{args.profile!r} {result.run_id}"
                )
                print(hint, file=sys.stderr)
            return 1 if result.failed else 0

    except ProfileValidationError as exc:
        print(f"{parser.prog}: profile error: {exc}", file=sys.stderr)
        return 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

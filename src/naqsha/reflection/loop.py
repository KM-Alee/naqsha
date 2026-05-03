"""Reflection Loop implementation: gate, workspace, candidate files."""

from __future__ import annotations

import json
from pathlib import Path

from naqsha.protocols.qaoa import TraceEvent
from naqsha.reflection.base import ReflectionPatch, ReflectionPatchEventSink
from naqsha.reflection.candidate import build_candidate_markdown, build_meta_json
from naqsha.reflection.config import ReflectionTomlSettings, load_reflection_toml_settings
from naqsha.reflection.reliability_gate import (
    GateRunner,
    ReliabilityGateResult,
    resolve_project_root_for_gate,
    run_reliability_gate_subprocess,
)
from naqsha.reflection.rollback import AutomatedRollbackManager
from naqsha.reflection.workspace import assert_workspace_outside_package, create_isolated_workspace

_CANDIDATE_MD = "CANDIDATE.md"
_META_JSON = "meta.json"
_READINESS = "READY_FOR_REVIEW.txt"
_IMPROVEMENT_NOTES = "IMPROVEMENT_NOTES.md"
_MERGE_DIR = "merge"


def _write_merge_payload(team_workspace: Path, merge_dir: Path) -> None:
    """Populate ``merge_dir`` with a minimal ``naqsha.toml`` delta for auto-merge."""

    merge_dir.mkdir(parents=True, exist_ok=True)
    src = team_workspace / "naqsha.toml"
    if src.is_file():
        marker = "\n\n# naqsha: reflection auto-merge marker\n"
        body = src.read_text(encoding="utf-8").rstrip() + marker
        (merge_dir / "naqsha.toml").write_text(body, encoding="utf-8")


class SimpleReflectionLoop:
    """Builds isolated Reflection Patch folders from a QAOA trace.

    This class does not import or call Tool Policy, the Core Runtime, or model adapters.
    """

    def __init__(
        self,
        *,
        workspace_parent: Path,
        team_workspace: Path | None = None,
        project_root: Path | None = None,
        gate_runner: GateRunner | None = None,
        rollback_manager: AutomatedRollbackManager | None = None,
        reflection_settings: ReflectionTomlSettings | None = None,
        patch_event_sink: ReflectionPatchEventSink | None = None,
        orchestrator_agent_id: str = "",
    ) -> None:
        self._workspace_parent = workspace_parent
        self._team_workspace = (team_workspace or Path.cwd()).expanduser().resolve()
        self._project_root = project_root
        self._gate_runner: GateRunner = gate_runner or run_reliability_gate_subprocess
        self._rollback = rollback_manager or AutomatedRollbackManager()
        self._reflection_settings = reflection_settings
        self._patch_event_sink = patch_event_sink
        self._orchestrator_agent_id = orchestrator_agent_id

    def propose_patch(self, trace: list[TraceEvent]) -> ReflectionPatch | None:
        if not trace:
            return None

        settings = self._reflection_settings or load_reflection_toml_settings(self._team_workspace)

        root = self._project_root
        if root is None:
            root = resolve_project_root_for_gate()

        gate_result: ReliabilityGateResult | None = None
        passed = False
        if root is None:
            gate_result = ReliabilityGateResult(
                passed=False,
                returncode=-1,
                command=tuple(),
                stdout_tail="",
                stderr_tail=(
                    "Reliability Gate could not run: pass project_root= pointing at "
                    "a NAQSHA checkout that contains tests/."
                ),
            )
            passed = False
        else:
            gate_result = self._gate_runner(root)
            passed = gate_result.passed

        workspace = create_isolated_workspace(self._workspace_parent)

        effective_auto_merge = (
            settings.enabled
            and settings.auto_merge
            and passed
            and settings.reliability_gate
            and (self._team_workspace / "naqsha.toml").is_file()
        )

        md = build_candidate_markdown(trace, reliability_gate_passed=passed)
        (workspace / _CANDIDATE_MD).write_text(md, encoding="utf-8")

        auto_merged = False
        if effective_auto_merge:
            try:
                _write_merge_payload(self._team_workspace, workspace / _MERGE_DIR)
                patch_for_merge = ReflectionPatch(
                    workspace=workspace,
                    summary="",
                    reliability_gate_passed=True,
                    auto_merged=True,
                )
                self._rollback.merge_patch(
                    patch_for_merge,
                    team_workspace=self._team_workspace,
                    run_id=trace[0].run_id,
                    agent_id=self._orchestrator_agent_id,
                    event_sink=self._patch_event_sink,
                )
                auto_merged = True
            except (OSError, ValueError):
                auto_merged = False

        meta = build_meta_json(
            trace,
            reliability_gate_passed=passed,
            gate_result=gate_result,
            auto_merged=auto_merged,
        )
        (workspace / _META_JSON).write_text(meta, encoding="utf-8")

        if passed:
            msg = (
                "Reliability Gate passed. Human review is still required before any merge.\n"
                if not auto_merged
                else (
                    "Reliability Gate passed; patch was auto-merged into this team workspace. "
                    "Boot verification will run on the next agent run.\n"
                )
            )
            (workspace / _READINESS).write_text(msg, encoding="utf-8")
        else:
            (workspace / "GATE_FAILED.txt").write_text(
                "Reliability Gate did not pass. Do not treat this folder as review-ready.\n",
                encoding="utf-8",
            )

        notes = (
            "# Reviewed self-improvement\n\n"
            "- Read `CANDIDATE.md` and `meta.json` in this workspace.\n"
            "- Optional: save regression expectations with `naqsha eval save ...` "
            "into `.naqsha/evals/` and reference them when reviewing.\n"
        )
        if auto_merged:
            notes += (
                "- This patch was auto-merged per `[reflection] auto_merge = true`; "
                "the Automated Rollback Manager snapshots `naqsha.toml` and `tools/` "
                "before merge.\n"
            )
        else:
            notes += "- Do not merge or hotpatch the active runtime without human approval.\n"
        (workspace / _IMPROVEMENT_NOTES).write_text(notes, encoding="utf-8")

        short = (
            f"run {trace[0].run_id}: gate {'ok' if passed else 'failed'}; "
            f"see {workspace / _CANDIDATE_MD}"
        )
        if auto_merged:
            short += "; auto-merged into team workspace"

        return ReflectionPatch(
            workspace=workspace,
            summary=short,
            reliability_gate_passed=passed,
            auto_merged=auto_merged,
        )


def noop_gate_runner(_project_root: Path) -> ReliabilityGateResult:
    """Test helper: gate always passes."""

    return ReliabilityGateResult(
        passed=True,
        returncode=0,
        command=("noop",),
        stdout_tail="",
        stderr_tail="",
    )


def failing_gate_runner(_project_root: Path) -> ReliabilityGateResult:
    """Test helper: gate always fails."""

    return ReliabilityGateResult(
        passed=False,
        returncode=1,
        command=("noop-fail",),
        stdout_tail="",
        stderr_tail="synthetic failure",
    )


def list_reflection_patch_workspace_ids(workspace_parent: Path) -> list[str]:
    """Return patch workspace directory names (``reflection-patch-*``) newest first."""

    parent = workspace_parent.expanduser().resolve()
    if not parent.is_dir():
        return []
    names: list[str] = []
    for p in sorted(parent.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.is_dir() and p.name.startswith("reflection-patch-"):
            names.append(p.name)
    return names


def read_patch_review_texts(
    patch_id: str,
    *,
    team_workspace: Path,
    workspace_parent: Path,
) -> tuple[str, str]:
    """Load ``naqsha.toml`` text from the team root and from ``patch.merge/`` (if present)."""

    team = team_workspace.expanduser().resolve()
    team_file = team / "naqsha.toml"
    team_txt = (
        team_file.read_text(encoding="utf-8", errors="replace") if team_file.is_file() else ""
    )

    patch_ws = (workspace_parent.expanduser().resolve() / patch_id).resolve()
    proposed = patch_ws / _MERGE_DIR / "naqsha.toml"
    prop_txt = proposed.read_text(encoding="utf-8", errors="replace") if proposed.is_file() else ""
    return team_txt, prop_txt


def approve_patch(
    patch_id: str,
    *,
    team_workspace: Path,
    workspace_parent: Path,
    run_id: str | None = None,
    agent_id: str = "",
    rollback_manager: AutomatedRollbackManager | None = None,
    patch_event_sink: ReflectionPatchEventSink | None = None,
) -> None:
    """Apply a human-approved Reflection Patch merge into *team_workspace*.

    If the patch workspace has no ``merge/`` tree yet, it is populated from the
    current team ``naqsha.toml`` using the same marker payload as auto-merge.
    """

    team_workspace = team_workspace.expanduser().resolve()
    workspace_parent = workspace_parent.expanduser().resolve()
    patch_ws = (workspace_parent / patch_id).resolve()
    assert_workspace_outside_package(patch_ws, label="patch workspace")

    if not patch_ws.is_dir():
        msg = f"Unknown patch workspace {patch_id!r} under {workspace_parent}."
        raise ValueError(msg)

    merge_dir = patch_ws / _MERGE_DIR
    if not merge_dir.is_dir():
        _write_merge_payload(team_workspace, merge_dir)

    rid = run_id or "manual-approve"
    meta_path = patch_ws / _META_JSON
    if meta_path.is_file():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("run_id"):
                rid = str(data["run_id"])
        except json.JSONDecodeError:
            pass

    patch = ReflectionPatch(
        workspace=patch_ws,
        summary=f"approved:{patch_id}",
        reliability_gate_passed=True,
        auto_merged=False,
    )
    mgr = rollback_manager or AutomatedRollbackManager()
    mgr.merge_patch(
        patch,
        team_workspace=team_workspace,
        run_id=rid,
        agent_id=agent_id,
        event_sink=patch_event_sink,
    )


def reject_patch(patch_id: str, *, workspace_parent: Path) -> None:
    """Record a rejection for a patch workspace without merging into the team tree."""

    workspace_parent = workspace_parent.expanduser().resolve()
    patch_ws = (workspace_parent / patch_id).resolve()
    assert_workspace_outside_package(patch_ws, label="patch workspace")

    if not patch_ws.is_dir():
        msg = f"Unknown patch workspace {patch_id!r} under {workspace_parent}."
        raise ValueError(msg)

    (patch_ws / "PATCH_REJECTED.txt").write_text(
        "This Reflection Patch was rejected from the Workbench; no merge was applied.\n",
        encoding="utf-8",
    )

"""Reflection Loop implementation: gate, workspace, candidate files."""

from __future__ import annotations

from pathlib import Path

from naqsha.protocols.qaoa import TraceEvent
from naqsha.reflection.base import ReflectionPatch
from naqsha.reflection.candidate import build_candidate_markdown, build_meta_json
from naqsha.reflection.reliability_gate import (
    GateRunner,
    ReliabilityGateResult,
    resolve_project_root_for_gate,
    run_reliability_gate_subprocess,
)
from naqsha.reflection.workspace import create_isolated_workspace

_CANDIDATE_MD = "CANDIDATE.md"
_META_JSON = "meta.json"
_READINESS = "READY_FOR_REVIEW.txt"
_IMPROVEMENT_NOTES = "IMPROVEMENT_NOTES.md"


class SimpleReflectionLoop:
    """Builds isolated Reflection Patch folders from a QAOA trace.

    This class does not import or call Tool Policy, the Core Runtime, or model adapters.
    """

    def __init__(
        self,
        *,
        workspace_parent: Path,
        project_root: Path | None = None,
        gate_runner: GateRunner | None = None,
    ) -> None:
        self._workspace_parent = workspace_parent
        self._project_root = project_root
        self._gate_runner: GateRunner = gate_runner or run_reliability_gate_subprocess

    def propose_patch(self, trace: list[TraceEvent]) -> ReflectionPatch | None:
        if not trace:
            return None

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
        else:
            gate_result = self._gate_runner(root)
            passed = gate_result.passed

        workspace = create_isolated_workspace(self._workspace_parent)

        md = build_candidate_markdown(trace, reliability_gate_passed=passed)
        (workspace / _CANDIDATE_MD).write_text(md, encoding="utf-8")

        meta = build_meta_json(trace, reliability_gate_passed=passed, gate_result=gate_result)
        (workspace / _META_JSON).write_text(meta, encoding="utf-8")

        if passed:
            (workspace / _READINESS).write_text(
                "Reliability Gate passed. Human review is still required before any merge.\n",
                encoding="utf-8",
            )
        else:
            (workspace / "GATE_FAILED.txt").write_text(
                "Reliability Gate did not pass. Do not treat this folder as review-ready.\n",
                encoding="utf-8",
            )

        (workspace / _IMPROVEMENT_NOTES).write_text(
            "# Reviewed self-improvement\n\n"
            "- Read `CANDIDATE.md` and `meta.json` in this workspace.\n"
            "- Optional: save regression expectations with `naqsha eval save ...` "
            "into `.naqsha/evals/` and reference them when reviewing.\n"
            "- Do not merge or hotpatch the active runtime without human approval.\n",
            encoding="utf-8",
        )

        short = (
            f"run {trace[0].run_id}: gate {'ok' if passed else 'failed'}; "
            f"see {workspace / _CANDIDATE_MD}"
        )
        return ReflectionPatch(
            workspace=workspace,
            summary=short,
            reliability_gate_passed=passed,
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

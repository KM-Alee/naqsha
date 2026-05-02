"""Reliability Gate: executable checks before a Reflection Patch is review-ready."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# PRD Reliability Gate scope: replay, protocol/schema, policy+trace, SimpleMem-Cross, red-team.
RELIABILITY_GATE_TEST_PATHS: tuple[str, ...] = (
    "tests/test_trace_replay.py",
    "tests/test_protocols.py",
    "tests/test_policy_and_trace.py",
    "tests/test_memory_simplemem_cross.py",
    "tests/redteam/test_corpus.py",
)


@dataclass(frozen=True)
class ReliabilityGateResult:
    passed: bool
    returncode: int
    command: tuple[str, ...]
    stdout_tail: str
    stderr_tail: str


def resolve_project_root_for_gate() -> Path | None:
    """Find a development checkout root that contains the gate test files."""

    here = Path(__file__).resolve().parent
    for base in [here] + list(here.parents):
        relay = base / RELIABILITY_GATE_TEST_PATHS[0]
        if relay.is_file():
            return base
    return None


def _truncate(s: str, max_chars: int = 4000) -> str:
    if len(s) <= max_chars:
        return s
    return s[-max_chars:]


def run_reliability_gate_subprocess(project_root: Path) -> ReliabilityGateResult:
    """Run pytest on the Reliability Gate corpus (blocking)."""

    root = project_root.resolve()
    missing = [p for p in RELIABILITY_GATE_TEST_PATHS if not (root / p).is_file()]
    if missing:
        return ReliabilityGateResult(
            passed=False,
            returncode=-1,
            command=tuple(),
            stdout_tail="",
            stderr_tail=(
                "Reliability Gate tests missing under project root "
                f"{root}: {', '.join(missing)}"
            ),
        )

    argv = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        *[str(root / p) for p in RELIABILITY_GATE_TEST_PATHS],
    ]
    proc = subprocess.run(
        argv,
        cwd=root,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    return ReliabilityGateResult(
        passed=proc.returncode == 0,
        returncode=proc.returncode,
        command=tuple(argv),
        stdout_tail=_truncate(proc.stdout or ""),
        stderr_tail=_truncate(proc.stderr or ""),
    )


GateRunner = Callable[[Path], ReliabilityGateResult]

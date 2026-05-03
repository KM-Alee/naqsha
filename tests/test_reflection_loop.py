"""Reflection Loop boundary: workspace isolation, Reliability Gate, no runtime hotpatch."""

from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

import naqsha
from naqsha import cli
from naqsha.protocols.qaoa import answer_event, failure_event, query_event
from naqsha.reflection.loop import (
    SimpleReflectionLoop,
    failing_gate_runner,
    noop_gate_runner,
)
from naqsha.reflection.reliability_gate import resolve_project_root_for_gate
from naqsha.reflection.workspace import (
    ReflectionWorkspaceError,
    create_isolated_workspace,
    naqsha_package_dir,
)


def _reflection_py_files() -> list[Path]:
    pkg = Path(naqsha.__file__).resolve().parent / "reflection"
    return sorted(pkg.glob("*.py"))


def test_reflection_package_does_not_import_policy_or_runtime() -> None:
    forbidden = ("naqsha.policy", "naqsha.runtime", "naqsha.approvals", "CoreRuntime", "ToolPolicy")
    for path in _reflection_py_files():
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path.name} must not reference {token}"


def test_workspace_rejects_parent_inside_naqsha_package(tmp_path: Path) -> None:
    pkg = naqsha_package_dir()
    with pytest.raises(ReflectionWorkspaceError):
        create_isolated_workspace(pkg)


def test_propose_patch_noop_gate_writes_artifacts(tmp_path: Path) -> None:
    run_id = "r1"
    events = [
        query_event(run_id, "hello"),
        answer_event(run_id, "done"),
    ]
    loop = SimpleReflectionLoop(
        workspace_parent=tmp_path,
        team_workspace=tmp_path,
        project_root=tmp_path,
        gate_runner=noop_gate_runner,
    )
    patch = loop.propose_patch(events)
    assert patch is not None
    assert patch.reliability_gate_passed is True
    assert patch.ready_for_human_review is True
    ws = patch.workspace
    assert ws.is_dir()
    assert (ws / "CANDIDATE.md").is_file()
    assert (ws / "meta.json").is_file()
    assert (ws / "READY_FOR_REVIEW.txt").is_file()
    assert (ws / "IMPROVEMENT_NOTES.md").is_file()
    body = (ws / "CANDIDATE.md").read_text(encoding="utf-8")
    assert run_id in body
    assert "done" in body
    meta = json.loads((ws / "meta.json").read_text(encoding="utf-8"))
    assert meta.get("auto_merged") is False


def test_propose_patch_failing_gate_not_review_ready(tmp_path: Path) -> None:
    run_id = "r2"
    events = [query_event(run_id, "q"), failure_event(run_id, "budget", "max steps")]
    loop = SimpleReflectionLoop(
        workspace_parent=tmp_path,
        team_workspace=tmp_path,
        project_root=tmp_path,
        gate_runner=failing_gate_runner,
    )
    patch = loop.propose_patch(events)
    assert patch is not None
    assert patch.reliability_gate_passed is False
    assert patch.ready_for_human_review is False
    assert (patch.workspace / "GATE_FAILED.txt").is_file()
    meta = json.loads((patch.workspace / "meta.json").read_text(encoding="utf-8"))
    assert meta["reliability_gate_passed"] is False
    assert meta["ready_for_human_review"] is False


def test_propose_patch_empty_trace_returns_none(tmp_path: Path) -> None:
    loop = SimpleReflectionLoop(
        workspace_parent=tmp_path,
        team_workspace=tmp_path,
        project_root=tmp_path,
        gate_runner=noop_gate_runner,
    )
    assert loop.propose_patch([]) is None


def test_reflection_patch_has_no_merge_or_apply() -> None:
    from naqsha.reflection.base import ReflectionPatch

    public = {n for n in dir(ReflectionPatch) if not n.startswith("_")}
    assert "merge" not in public
    assert "apply" not in public
    assert "hotpatch" not in public


def test_resolve_project_root_for_gate_in_checkout() -> None:
    root = resolve_project_root_for_gate()
    assert root is not None
    assert (root / "tests" / "test_trace_replay.py").is_file()


def test_cli_reflect_writes_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    buf = StringIO()
    with redirect_stdout(buf):
        assert cli.main(["run", "--profile", "local-fake", "ping"]) == 0
    run_id = json.loads(buf.getvalue())["run_id"]

    class FastReflectLoop(SimpleReflectionLoop):
        def __init__(self, **kwargs):
            super().__init__(gate_runner=noop_gate_runner, **kwargs)

    monkeypatch.setattr(cli, "SimpleReflectionLoop", FastReflectLoop)

    out = StringIO()
    with redirect_stdout(out):
        code = cli.main(
            [
                "reflect",
                "--profile",
                "local-fake",
                "--workspace-base",
                str(tmp_path / "rw"),
                run_id,
            ]
        )
    assert code == 0
    payload = json.loads(out.getvalue())
    assert payload["reliability_gate_passed"] is True
    assert Path(payload["workspace"]).is_dir()

"""Human approve / reject APIs for Reflection Patch workspaces."""

from __future__ import annotations

from pathlib import Path

from naqsha.protocols.qaoa import answer_event, query_event
from naqsha.reflection.config import ReflectionTomlSettings
from naqsha.reflection.loop import (
    SimpleReflectionLoop,
    approve_patch,
    list_reflection_patch_workspace_ids,
    noop_gate_runner,
    read_patch_review_texts,
    reject_patch,
)


def _team_toml() -> str:
    return "\n".join(
        [
            '[workspace]',
            'name = "t"',
            'orchestrator = "orch"',
            "",
            '[agents.orch]',
            'role = "orchestrator"',
            'model_adapter = "fake"',
            'tools = ["clock"]',
            "",
            "[reflection]",
            "enabled = true",
            "auto_merge = false",
            "reliability_gate = true",
            "",
        ]
    )


def test_list_and_read_patch_review_texts(tmp_path: Path) -> None:
    team = tmp_path / "team"
    team.mkdir()
    (team / "naqsha.toml").write_text("a=1\n", encoding="utf-8")
    rw = tmp_path / "rw"
    rw.mkdir()
    loop = SimpleReflectionLoop(
        workspace_parent=rw,
        team_workspace=team,
        project_root=tmp_path,
        gate_runner=noop_gate_runner,
        reflection_settings=ReflectionTomlSettings(
            enabled=True,
            auto_merge=False,
            reliability_gate=True,
        ),
    )
    patch = loop.propose_patch([query_event("r", "q"), answer_event("r", "a")])
    assert patch is not None
    pid = patch.workspace.name
    assert pid in list_reflection_patch_workspace_ids(rw)
    left, right = read_patch_review_texts(pid, team_workspace=team, workspace_parent=rw)
    assert "a=1" in left
    assert right == ""

    merge = patch.workspace / "merge"
    merge.mkdir(exist_ok=True)
    (merge / "naqsha.toml").write_text("b=2\n", encoding="utf-8")
    left2, right2 = read_patch_review_texts(pid, team_workspace=team, workspace_parent=rw)
    assert left2 == left
    assert "b=2" in right2


def test_approve_patch_creates_merge_and_merges(tmp_path: Path) -> None:
    team = tmp_path / "team"
    team.mkdir()
    body = _team_toml()
    (team / "naqsha.toml").write_text(body, encoding="utf-8")
    rw = tmp_path / "rw"
    rw.mkdir()

    class _Sink:
        def __init__(self) -> None:
            self.auto: bool | None = None

        def patch_merged(
            self,
            *,
            run_id: str,
            agent_id: str,
            patch_id: str,
            auto_merged: bool,
        ) -> None:
            self.auto = auto_merged

        def patch_rolled_back(
            self,
            *,
            run_id: str,
            agent_id: str,
            patch_id: str,
            reason: str,
        ) -> None:
            pass

    sink = _Sink()
    loop = SimpleReflectionLoop(
        workspace_parent=rw,
        team_workspace=team,
        project_root=tmp_path,
        gate_runner=noop_gate_runner,
        reflection_settings=ReflectionTomlSettings(
            enabled=True,
            auto_merge=False,
            reliability_gate=True,
        ),
    )
    patch = loop.propose_patch([query_event("run1", "q"), answer_event("run1", "a")])
    assert patch is not None
    pid = patch.workspace.name
    assert not (patch.workspace / "merge").exists()

    approve_patch(pid, team_workspace=team, workspace_parent=rw, patch_event_sink=sink)

    assert (team / ".naqsha" / "boot_status").read_text(encoding="utf-8").strip() == "pending"
    merged = (team / "naqsha.toml").read_text(encoding="utf-8")
    assert "# naqsha: reflection auto-merge marker" in merged
    assert sink.auto is False


def test_reject_patch_writes_marker(tmp_path: Path) -> None:
    team = tmp_path / "team"
    team.mkdir()
    (team / "naqsha.toml").write_text(_team_toml(), encoding="utf-8")
    rw = tmp_path / "rw"
    rw.mkdir()
    loop = SimpleReflectionLoop(
        workspace_parent=rw,
        team_workspace=team,
        project_root=tmp_path,
        gate_runner=noop_gate_runner,
        reflection_settings=ReflectionTomlSettings(
            enabled=True,
            auto_merge=False,
            reliability_gate=True,
        ),
    )
    patch = loop.propose_patch([query_event("r", "q"), answer_event("r", "a")])
    assert patch is not None
    pid = patch.workspace.name
    reject_patch(pid, workspace_parent=rw)
    assert (patch.workspace / "PATCH_REJECTED.txt").is_file()
    assert (team / "naqsha.toml").read_text(encoding="utf-8") == _team_toml()

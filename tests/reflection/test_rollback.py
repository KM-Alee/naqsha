"""Automated Rollback Manager: backup, restore, pruning."""

from __future__ import annotations

from pathlib import Path

from naqsha.reflection.base import ReflectionPatch
from naqsha.reflection.rollback import MAX_BACKUPS, AutomatedRollbackManager


def _write_team_toml(team: Path, body: str) -> None:
    team.mkdir(parents=True, exist_ok=True)
    (team / "naqsha.toml").write_text(body, encoding="utf-8")


def _naq(team: Path) -> Path:
    return team / ".naqsha"


def _patch_with_merge(workspace_parent: Path, merge_body: str) -> ReflectionPatch:
    patch_root = workspace_parent / "patch-ws"
    merge = patch_root / "merge"
    merge.mkdir(parents=True, exist_ok=True)
    (merge / "naqsha.toml").write_text(merge_body, encoding="utf-8")
    return ReflectionPatch(
        workspace=patch_root,
        summary="test",
        reliability_gate_passed=True,
        auto_merged=False,
    )


def test_merge_creates_backup_and_sets_pending(tmp_path: Path) -> None:
    team = tmp_path / "team"
    original = "[workspace]\nname = \"x\"\norchestrator = \"a\"\n"
    _write_team_toml(team, original)

    mgr = AutomatedRollbackManager()
    patch = _patch_with_merge(tmp_path, original + "\n# merged-line\n")
    mgr.merge_patch(
        patch,
        team_workspace=team,
        run_id="r1",
        agent_id="orch",
        event_sink=None,
    )

    assert (_naq(team) / "boot_status").read_text(encoding="utf-8").strip() == "pending"
    backups = sorted((_naq(team) / "backups").iterdir())
    assert len(backups) == 1
    restored_from = backups[0] / "naqsha.toml"
    assert restored_from.read_text(encoding="utf-8") == original
    assert "# merged-line" in (team / "naqsha.toml").read_text(encoding="utf-8")


def test_boot_failure_restores_backup(tmp_path: Path) -> None:
    team = tmp_path / "team"
    original = "[workspace]\nname = \"x\"\norchestrator = \"a\"\n"
    _write_team_toml(team, original)

    mgr = AutomatedRollbackManager()
    patch = _patch_with_merge(tmp_path, original + "\n# merged-line\n")
    mgr.merge_patch(patch, team_workspace=team, run_id="run-x", agent_id="a")

    assert (_naq(team) / "last_merge_meta.json").is_file()

    mgr.verify_boot_if_pending(team, health_check=lambda: False, event_sink=None)

    assert (team / "naqsha.toml").read_text(encoding="utf-8") == original
    assert (_naq(team) / "boot_status").read_text(encoding="utf-8").strip() == "rolled_back"


def test_boot_success_sets_stable(tmp_path: Path) -> None:
    team = tmp_path / "team"
    _write_team_toml(team, "[workspace]\nname = \"x\"\norchestrator = \"a\"\n")

    mgr = AutomatedRollbackManager()
    patch = _patch_with_merge(tmp_path, "[workspace]\nname = \"y\"\n")
    mgr.merge_patch(patch, team_workspace=team, run_id="r", agent_id="")

    mgr.verify_boot_if_pending(team, health_check=lambda: True, event_sink=None)
    assert (_naq(team) / "boot_status").read_text(encoding="utf-8").strip() == "stable"


def test_backup_rotation_keeps_five(tmp_path: Path) -> None:
    team = tmp_path / "team"
    base_toml = "[workspace]\nname = \"x\"\norchestrator = \"a\"\n"
    _write_team_toml(team, base_toml)

    mgr = AutomatedRollbackManager()
    for i in range(MAX_BACKUPS + 2):
        patch_root = tmp_path / f"pw{i}"
        merge = patch_root / "merge"
        merge.mkdir(parents=True, exist_ok=True)
        (merge / "naqsha.toml").write_text(base_toml + f"\n# rev={i}\n", encoding="utf-8")
        patch = ReflectionPatch(workspace=patch_root, summary="s", reliability_gate_passed=True)
        mgr.merge_patch(patch, team_workspace=team, run_id="r", agent_id="")

    backups_root = _naq(team) / "backups"
    dirs = [p for p in backups_root.iterdir() if p.is_dir()]
    assert len(dirs) == MAX_BACKUPS


def test_event_sink_records_merge_and_rollback(tmp_path: Path) -> None:
    recorded: list[tuple[str, dict[str, object]]] = []

    class Sink:
        def patch_merged(
            self,
            *,
            run_id: str,
            agent_id: str,
            patch_id: str,
            auto_merged: bool,
        ) -> None:
            recorded.append(("merged", {"run_id": run_id, "patch_id": patch_id}))

        def patch_rolled_back(
            self,
            *,
            run_id: str,
            agent_id: str,
            patch_id: str,
            reason: str,
        ) -> None:
            recorded.append(("rolled", {"patch_id": patch_id, "reason": reason}))

    team = tmp_path / "team"
    _write_team_toml(team, "[w]\nx=1\n")

    sink = Sink()
    mgr = AutomatedRollbackManager()
    patch = _patch_with_merge(tmp_path, "[w]\nx=2\n")
    mgr.merge_patch(patch, team_workspace=team, run_id="rid", agent_id="aid", event_sink=sink)

    assert recorded and recorded[0][0] == "merged"
    assert recorded[0][1]["run_id"] == "rid"

    mgr.verify_boot_if_pending(team, health_check=lambda: False, event_sink=sink)
    assert any(r[0] == "rolled" for r in recorded)


def test_rolled_back_cleared_only_after_health_pass(tmp_path: Path) -> None:
    team = tmp_path / "team"
    _write_team_toml(team, "[w]\nx=1\n")
    _naq(team).mkdir(parents=True, exist_ok=True)
    (_naq(team) / "boot_status").write_text("rolled_back\n", encoding="utf-8")

    mgr = AutomatedRollbackManager()
    mgr.verify_boot_if_pending(team, health_check=lambda: False, event_sink=None)
    assert (_naq(team) / "boot_status").read_text(encoding="utf-8").strip() == "rolled_back"

    mgr.verify_boot_if_pending(team, health_check=lambda: True, event_sink=None)
    assert (_naq(team) / "boot_status").read_text(encoding="utf-8").strip() == "stable"


def test_ambiguous_backup_without_meta_does_not_restore(tmp_path: Path) -> None:
    team = tmp_path / "team"
    original = "[workspace]\nname = \"orig\"\n"
    merged = "[workspace]\nname = \"merged\"\n"
    _write_team_toml(team, merged)
    n = _naq(team)
    n.mkdir(parents=True, exist_ok=True)
    (n / "boot_status").write_text("pending\n", encoding="utf-8")
    backups = n / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    (backups / "older").mkdir()
    (backups / "older" / "naqsha.toml").write_text(original, encoding="utf-8")
    (backups / "newer").mkdir()
    (backups / "newer" / "naqsha.toml").write_text(original, encoding="utf-8")

    mgr = AutomatedRollbackManager()
    mgr.verify_boot_if_pending(team, health_check=lambda: False, event_sink=None)

    assert (team / "naqsha.toml").read_text(encoding="utf-8") == merged
    assert (_naq(team) / "boot_status").read_text(encoding="utf-8").strip() == "rolled_back"


def test_merge_patch_requires_merge_directory(tmp_path: Path) -> None:
    team = tmp_path / "team"
    _write_team_toml(team, "[w]\nx=1\n")
    empty = tmp_path / "empty"
    empty.mkdir()
    bad = ReflectionPatch(workspace=empty, summary="s", reliability_gate_passed=True)
    mgr = AutomatedRollbackManager()
    try:
        mgr.merge_patch(bad, team_workspace=team, run_id="x", agent_id="")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "merge" in str(exc).lower()

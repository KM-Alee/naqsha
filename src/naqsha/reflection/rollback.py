"""Automated Rollback Manager: snapshots before merge, boot verification, restore."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from naqsha.reflection.base import ReflectionPatch, ReflectionPatchEventSink

NAQSHA_DIR = ".naqsha"
BACKUPS_SUBDIR = "backups"
BOOT_STATUS_FILE = "boot_status"
LAST_MERGE_META = "last_merge_meta.json"
MAX_BACKUPS = 5

STATUS_PENDING = "pending"
STATUS_STABLE = "stable"
STATUS_ROLLED_BACK = "rolled_back"

_MERGE_DIR_NAME = "merge"


def _naqsha_dir(team_workspace: Path) -> Path:
    return team_workspace / NAQSHA_DIR


def _read_boot_status(team_workspace: Path) -> str | None:
    p = _naqsha_dir(team_workspace) / BOOT_STATUS_FILE
    if not p.is_file():
        return None
    return p.read_text(encoding="utf-8").strip() or None


def _write_boot_status(team_workspace: Path, status: str) -> None:
    d = _naqsha_dir(team_workspace)
    d.mkdir(parents=True, exist_ok=True)
    (d / BOOT_STATUS_FILE).write_text(status + "\n", encoding="utf-8")


def _safe_under_team(team_workspace: Path, dest: Path) -> bool:
    try:
        dest.resolve().relative_to(team_workspace.resolve())
    except ValueError:
        return False
    return True


def _backup_merge_targets(team_workspace: Path, backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    tom = team_workspace / "naqsha.toml"
    if tom.is_file():
        shutil.copy2(tom, backup_dir / "naqsha.toml")
    else:
        (backup_dir / ".no_naqsha_toml").write_text("", encoding="utf-8")

    tools = team_workspace / "tools"
    if tools.is_dir():
        shutil.copytree(tools, backup_dir / "tools", dirs_exist_ok=True)
    else:
        (backup_dir / ".no_tools_dir").write_text("", encoding="utf-8")


def _restore_merge_targets(team_workspace: Path, backup_dir: Path) -> None:
    tom_b = backup_dir / "naqsha.toml"
    if tom_b.is_file():
        team_workspace.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tom_b, team_workspace / "naqsha.toml")
    elif (backup_dir / ".no_naqsha_toml").is_file():
        (team_workspace / "naqsha.toml").unlink(missing_ok=True)

    if (backup_dir / ".no_tools_dir").is_file():
        shutil.rmtree(team_workspace / "tools", ignore_errors=True)
    elif (backup_dir / "tools").is_dir():
        tgt = team_workspace / "tools"
        if tgt.exists():
            shutil.rmtree(tgt)
        shutil.copytree(backup_dir / "tools", tgt)


def _apply_merge_tree(patch_merge_root: Path, team_workspace: Path) -> None:
    if not patch_merge_root.is_dir():
        return
    team_resolved = team_workspace.resolve()
    for path in patch_merge_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(patch_merge_root)
        dest = (team_workspace / rel).resolve()
        if not _safe_under_team(team_resolved, dest):
            msg = f"Unsafe merge path {rel!s}"
            raise ValueError(msg)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)


def _prune_backups(backups_root: Path) -> None:
    if not backups_root.is_dir():
        return
    dirs = sorted(
        (p for p in backups_root.iterdir() if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )
    for old in dirs[MAX_BACKUPS:]:
        shutil.rmtree(old, ignore_errors=True)


class AutomatedRollbackManager:
    """Snapshot ``naqsha.toml`` and ``tools/`` before merge; restore on failed boot."""

    def merge_patch(
        self,
        patch: ReflectionPatch,
        *,
        team_workspace: Path,
        run_id: str,
        agent_id: str = "",
        event_sink: ReflectionPatchEventSink | None = None,
    ) -> None:
        """Backup tracked files, apply ``patch.workspace/{merge}/``, set boot pending."""

        merge_src = patch.workspace / _MERGE_DIR_NAME
        if not merge_src.is_dir():
            msg = f"Patch workspace missing {_MERGE_DIR_NAME}/ directory for merge."
            raise ValueError(msg)

        team_workspace = team_workspace.expanduser().resolve()
        n = _naqsha_dir(team_workspace)
        n.mkdir(parents=True, exist_ok=True)
        backups_root = n / BACKUPS_SUBDIR
        backups_root.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%S_%f")
        backup_dir = backups_root / stamp
        _backup_merge_targets(team_workspace, backup_dir)

        _apply_merge_tree(merge_src, team_workspace)

        patch_id = patch.workspace.name
        meta: dict[str, Any] = {
            "patch_id": patch_id,
            "run_id": run_id,
            "agent_id": agent_id,
            "backup_name": backup_dir.name,
        }
        meta_text = json.dumps(meta, indent=2, sort_keys=True)
        (n / LAST_MERGE_META).write_text(meta_text, encoding="utf-8")
        _write_boot_status(team_workspace, STATUS_PENDING)
        _prune_backups(backups_root)

        if event_sink is not None:
            event_sink.patch_merged(
                run_id=run_id,
                agent_id=agent_id,
                patch_id=patch_id,
                auto_merged=patch.auto_merged,
            )

    def verify_boot_if_pending(
        self,
        team_workspace: Path,
        *,
        health_check: Callable[[], bool],
        event_sink: ReflectionPatchEventSink | None = None,
    ) -> bool:
        """If boot status is ``pending``, run *health_check*; rollback on failure."""

        team_workspace = team_workspace.expanduser().resolve()
        status = _read_boot_status(team_workspace)

        if status == STATUS_ROLLED_BACK:
            if health_check():
                _write_boot_status(team_workspace, STATUS_STABLE)
            return True

        if status != STATUS_PENDING:
            return True

        if health_check():
            _write_boot_status(team_workspace, STATUS_STABLE)
            return True

        n = _naqsha_dir(team_workspace)
        meta_path = n / LAST_MERGE_META
        backup_name: str | None = None
        patch_id = ""
        run_id = ""
        agent_id = ""
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                backup_name = meta.get("backup_name") if isinstance(meta, dict) else None
                patch_id = str(meta.get("patch_id", "")) if isinstance(meta, dict) else ""
                run_id = str(meta.get("run_id", "")) if isinstance(meta, dict) else ""
                agent_id = str(meta.get("agent_id", "")) if isinstance(meta, dict) else ""
            except json.JSONDecodeError:
                backup_name = None

        backups_root = n / BACKUPS_SUBDIR
        backup_dir: Path | None = None
        if backup_name and (backups_root / backup_name).is_dir():
            backup_dir = backups_root / backup_name
        else:
            dirs = sorted(
                (p for p in backups_root.iterdir() if p.is_dir()),
                key=lambda p: p.name,
                reverse=True,
            )
            if len(dirs) == 1:
                backup_dir = dirs[0]
            else:
                backup_dir = None

        reason = "Boot health check failed after auto-merge."
        if backup_dir is not None:
            _restore_merge_targets(team_workspace, backup_dir)
        else:
            reason += (
                " No unambiguous backup (need valid last_merge_meta or exactly one backup); "
                "workspace left unchanged."
            )

        _write_boot_status(team_workspace, STATUS_ROLLED_BACK)

        if event_sink is not None:
            event_sink.patch_rolled_back(
                run_id=run_id,
                agent_id=agent_id,
                patch_id=patch_id or "unknown",
                reason=reason,
            )

        return True

"""Isolated Reflection Patch workspaces (never the active package tree)."""

from __future__ import annotations

import uuid
from pathlib import Path

import naqsha


class ReflectionWorkspaceError(ValueError):
    """Reflection would write inside the naqsha package tree or another forbidden path."""


def naqsha_package_dir() -> Path:
    return Path(naqsha.__file__).resolve().parent


def assert_workspace_outside_package(path: Path, *, label: str = "path") -> None:
    """Ensure ``path`` is not inside the installed ``naqsha`` package directory."""

    pkg = naqsha_package_dir()
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(pkg)
    except ValueError:
        return
    raise ReflectionWorkspaceError(
        f"{label} {resolved} must not lie inside the naqsha package directory {pkg}."
    )


def create_isolated_workspace(parent: Path, *, prefix: str = "reflection-patch") -> Path:
    """Create ``parent / {prefix}-{uuid}`` after validating ``parent``."""

    assert_workspace_outside_package(parent, label="workspace_parent")
    parent.mkdir(parents=True, exist_ok=True)
    sub = parent / f"{prefix}-{uuid.uuid4().hex[:10]}"
    sub.mkdir(parents=False, exist_ok=False)
    assert_workspace_outside_package(sub, label="workspace")
    return sub

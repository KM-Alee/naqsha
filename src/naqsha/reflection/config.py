"""Load reflection-related settings from ``naqsha.toml`` (no Core Runtime imports)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ReflectionTomlSettings:
    """Subset of ``[reflection]`` used by ``SimpleReflectionLoop``.

    ``reliability_gate`` does **not** skip pytest for patch eligibility: it only gates whether
    ``auto_merge`` may run after the gate passes (fail-closed for autonomous merges).
    """

    enabled: bool = False
    auto_merge: bool = False
    reliability_gate: bool = True


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def load_reflection_toml_settings(team_workspace: Path) -> ReflectionTomlSettings:
    """Parse ``[reflection]`` from ``team_workspace/naqsha.toml`` if present."""

    path = team_workspace / "naqsha.toml"
    if not path.is_file():
        return ReflectionTomlSettings()
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    blob = data.get("reflection")
    if not isinstance(blob, dict):
        return ReflectionTomlSettings()
    return ReflectionTomlSettings(
        enabled=_as_bool(blob.get("enabled", False), False),
        auto_merge=_as_bool(blob.get("auto_merge", False), False),
        reliability_gate=_as_bool(blob.get("reliability_gate", True), True),
    )

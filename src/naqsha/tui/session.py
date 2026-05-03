"""Persist Command Center preferences under ``.naqsha/sessions/``."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_SESSION_VERSION = 1


@dataclass
class CommandCenterSession:
    version: int = _SESSION_VERSION
    last_query: str = ""
    active_profile_name: str = ""
    #: Reserved for richer layout docking (serialized light-weight hints).
    layout_hint: dict[str, Any] | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, raw: str) -> CommandCenterSession:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return cls()
        ver = data.get("version", _SESSION_VERSION)
        try:
            if int(ver) != _SESSION_VERSION:
                return cls()
        except (TypeError, ValueError):
            return cls()
        lh = data.get("layout_hint")
        if lh is not None and not isinstance(lh, dict):
            lh = None
        return cls(
            version=_SESSION_VERSION,
            last_query=str(data.get("last_query", "")),
            active_profile_name=str(data.get("active_profile_name", "")),
            layout_hint=lh,
        )


def sessions_dir(workspace: Path) -> Path:
    base = workspace.expanduser().resolve() / ".naqsha" / "sessions"
    base.mkdir(parents=True, exist_ok=True)
    return base


def default_session_path(workspace: Path) -> Path:
    return sessions_dir(workspace) / "command-center.json"


def load_session(workspace: Path) -> CommandCenterSession:
    path = default_session_path(workspace)
    try:
        if not path.is_file():
            return CommandCenterSession()
        return CommandCenterSession.from_json(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return CommandCenterSession()


def save_session(workspace: Path, session: CommandCenterSession) -> None:
    path = default_session_path(workspace)
    try:
        path.write_text(session.to_json(), encoding="utf-8")
    except OSError:
        pass


def append_error_log(workspace: Path, line: str) -> None:
    log_root = workspace.expanduser().resolve() / ".naqsha" / "logs"
    try:
        log_root.mkdir(parents=True, exist_ok=True)
        lp = log_root / "command-center.log"
        with lp.open("a", encoding="utf-8") as fh:
            fh.write(line.rstrip("\n") + "\n")
    except OSError:
        pass

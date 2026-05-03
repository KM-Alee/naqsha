"""Team-wide Dynamic Memory Engine wiring.

All agents in a Team Workspace share one SQLite file and the same ``shared_`` namespace;
each agent uses a distinct ``private_<agent_id>_`` namespace.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from naqsha.memory.engine import DynamicMemoryEngine


@dataclass(frozen=True)
class TeamMemoryConfig:
    """Memory section from ``naqsha.toml``."""

    type: str = "sqlite"
    db_path: Path = Path(".naqsha/memory.db")
    embeddings: bool = False

    def resolve_paths(self, base_dir: Path) -> TeamMemoryConfig:
        path = self.db_path
        if not path.is_absolute():
            path = (base_dir / path).resolve()
        return TeamMemoryConfig(type=self.type, db_path=path, embeddings=self.embeddings)


def open_team_memory_engine(workspace_root: Path, config: TeamMemoryConfig) -> DynamicMemoryEngine:
    """Open the team SQLite database under the workspace root.

    The same engine instance must be passed to every agent CoreRuntime in that team so
    shared tables are truly shared.
    """
    resolved = config.resolve_paths(workspace_root)
    if resolved.type != "sqlite":
        raise ValueError(f"Unsupported memory type {resolved.type!r}; expected 'sqlite'.")
    return DynamicMemoryEngine(
        db_path=resolved.db_path,
        enable_embeddings=resolved.embeddings,
    )

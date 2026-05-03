"""Append-only JSONL Trace Store."""

from __future__ import annotations

import json
from pathlib import Path

from naqsha.tracing.protocols.qaoa import TraceEvent, TraceValidationError


class JsonlTraceStore:
    """Store QAOA Trace events as append-only JSONL files."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        return self.root / f"{run_id}.jsonl"

    def append(self, event: TraceEvent) -> None:
        with self._path(event.run_id).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")

    def load(self, run_id: str) -> list[TraceEvent]:
        path = self._path(run_id)
        if not path.exists():
            return []
        events: list[TraceEvent] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                try:
                    events.append(TraceEvent.from_dict(json.loads(line)))
                except (json.JSONDecodeError, TraceValidationError) as exc:
                    raise ValueError(f"Corrupted trace line {line_number} in {path}") from exc
        return events

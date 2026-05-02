"""In-memory Memory Port for deterministic tests."""

from __future__ import annotations

from naqsha.memory.base import MemoryRecord
from naqsha.tools.base import ToolObservation


class InMemoryMemoryPort:
    def __init__(self) -> None:
        self.records: list[MemoryRecord] = []
        self.started_runs: list[str] = []
        self.finished_runs: list[str] = []

    def start_run(self, run_id: str, query: str) -> None:
        self.started_runs.append(run_id)

    def retrieve(self, query: str, token_budget: int) -> list[MemoryRecord]:
        max_records = max(0, token_budget // 32)
        return self.records[-max_records:] if max_records else []

    def record_observation(self, run_id: str, tool: str, observation: ToolObservation) -> None:
        if observation.ok:
            self.records.append(
                MemoryRecord(content=observation.content, provenance=f"{run_id}:{tool}")
            )

    def finish_run(self, run_id: str, answer: str | None) -> None:
        self.finished_runs.append(run_id)

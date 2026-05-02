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
        cap = max(0, token_budget) * 4
        picked: list[MemoryRecord] = []
        spent = 0
        for rec in reversed(self.records):
            chunk = len(rec.content)
            if spent + chunk > cap and picked:
                break
            if spent + chunk > cap and not picked:
                body = rec.content[: max(0, cap - spent)]
                if not body.strip():
                    break
                picked.append(MemoryRecord(content=body, provenance=rec.provenance))
                spent = cap
                break
            picked.append(rec)
            spent += chunk
        return list(reversed(picked))

    def record_observation(self, run_id: str, tool: str, observation: ToolObservation) -> None:
        if observation.ok:
            self.records.append(
                MemoryRecord(content=observation.content, provenance=f"{run_id}:{tool}")
            )

    def finish_run(self, run_id: str, answer: str | None) -> None:
        self.finished_runs.append(run_id)

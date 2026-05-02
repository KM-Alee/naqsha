"""Memory Port semantics for the in-memory fake."""

from __future__ import annotations

from naqsha.memory.inmemory import InMemoryMemoryPort
from naqsha.tools.base import ToolObservation


def test_inmemory_records_only_successful_observations() -> None:
    mem = InMemoryMemoryPort()
    mem.start_run("r1", "q")
    mem.record_observation(
        "r1",
        "clock",
        ToolObservation(ok=False, content="error", metadata={"e": True}),
    )
    mem.record_observation(
        "r1",
        "clock",
        ToolObservation(ok=True, content="midnight UTC", metadata={}),
    )
    mem.finish_run("r1", "answered")
    assert len(mem.records) == 1
    assert mem.records[0].content == "midnight UTC"


def test_inmemory_retrieve_budgets_by_approx_char_quota() -> None:
    mem = InMemoryMemoryPort()
    mem.start_run("r1", "seed")
    for i in range(5):
        mem.record_observation(
            "r1",
            "echo",
            ToolObservation(ok=True, content="x" * 10, metadata={"i": i}),
        )
    mem.finish_run("r1", None)
    # token_budget=5 → 20 chars → two whole 10-char records at most.
    rows = mem.retrieve("any", token_budget=5)
    assert len(rows) == 2
    assert all(len(r.content) == 10 for r in rows)

"""Core Runtime emits streaming and budget events for the Typed Event Bus."""

from __future__ import annotations

from pathlib import Path

from naqsha.core.event_bus import RuntimeEventBus
from naqsha.core.events import BudgetProgress, StreamChunkReceived
from naqsha.profiles import parse_run_profile
from naqsha.wiring import build_runtime


def test_stream_chunks_emitted_for_final_answer(tmp_path: Path) -> None:
    (tmp_path / "traces").mkdir(parents=True)
    profile = parse_run_profile(
        {
            "name": "bus-stream",
            "model": "fake",
            "trace_dir": "traces",
            "tool_root": ".",
            "allowed_tools": None,
            "memory_adapter": "none",
            "auto_approve": True,
            "fake_model": {
                "messages": [{"kind": "answer", "text": "abcdefghijklmnop" * 3}],
            },
        },
        base_dir=tmp_path,
    )
    bus = RuntimeEventBus()
    got: list[object] = []
    bus.subscribe(got.append)
    rt = build_runtime(profile, event_bus=bus)
    res = rt.run("hello", run_id="fixed-run")
    assert not res.failed
    stream = [e for e in got if isinstance(e, StreamChunkReceived)]
    assert len(stream) >= 1
    assert "".join(e.chunk for e in stream) == "abcdefghijklmnop" * 3
    budgets = [e for e in got if isinstance(e, BudgetProgress)]
    assert budgets and budgets[0].steps_used >= 1

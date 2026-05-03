"""Flame panel tests."""

from __future__ import annotations

import pytest

pytest.importorskip("textual")

from datetime import UTC, datetime, timedelta

from textual.app import App, ComposeResult

from naqsha.core.events import RunStarted, SpanClosed, SpanOpened
from naqsha.tui.panels.flame import FlamePanel


@pytest.mark.asyncio
async def test_flame_panel_multi_agent_bars() -> None:
    class _Harness(App[None]):
        def compose(self) -> ComposeResult:
            yield FlamePanel(id="flame")

    t0 = datetime.now(tz=UTC)
    t1 = t0 + timedelta(seconds=0, milliseconds=500)

    async with _Harness().run_test() as pilot:
        panel = pilot.app.query_one(FlamePanel)
        panel.consume_event(RunStarted(run_id="r", agent_id="orch", query="q"))
        panel.consume_event(
            SpanOpened(
                run_id="r",
                trace_id="t",
                span_id="s-orch",
                parent_span_id=None,
                agent_id="orch",
                timestamp=t0,
            )
        )
        panel.consume_event(
            SpanOpened(
                run_id="r",
                trace_id="t",
                span_id="s-worker",
                parent_span_id="s-orch",
                agent_id="worker",
                timestamp=t0,
            )
        )
        panel.consume_event(
            SpanClosed(
                run_id="r",
                trace_id="t",
                span_id="s-worker",
                agent_id="worker",
                token_count=12,
                timestamp=t1,
            )
        )
        panel.consume_event(
            SpanClosed(
                run_id="r",
                trace_id="t",
                span_id="s-orch",
                agent_id="orch",
                token_count=5,
                timestamp=t1 + timedelta(seconds=1),
            )
        )
        await pilot.pause(0.05)
        times, toks = panel.metrics_snapshot()
    assert times["orch"] >= 1.0
    assert times["worker"] >= 0.0
    assert toks["orch"] == 5
    assert toks["worker"] == 12

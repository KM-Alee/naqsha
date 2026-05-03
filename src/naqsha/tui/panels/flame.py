"""Flame panel: per-agent wall time and token bars from span lifecycle events."""

from __future__ import annotations

from datetime import datetime

from textual.widgets import Static

from naqsha.core.events import RunCompleted, RunFailed, RunStarted, SpanClosed, SpanOpened


def _bar_blocks(p: float, bar_w: int, filled_style: str, empty_style: str) -> str:
    filled = min(bar_w, int(bar_w * p))
    empty = bar_w - filled
    return (
        f"[{filled_style}]{'█' * filled}[/]"
        f"[{empty_style}]{'░' * empty}[/]"
    )


class FlamePanel(Static):
    """Horizontal bars for span wall-clock duration and ``token_count`` by ``agent_id``."""

    DEFAULT_CSS = """
    FlamePanel {
        background: $surface;
        border: round $warning 22%;
        padding: 1;
        min-height: 8;
        content-align: left top;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__("", *args, **kwargs)
        self._opened: dict[str, tuple[datetime, str]] = {}
        self._time_by_agent: dict[str, float] = {}
        self._tok_by_agent: dict[str, int] = {}

    def consume_event(self, event: object) -> None:
        if isinstance(event, RunStarted):
            self._opened.clear()
            self._time_by_agent.clear()
            self._tok_by_agent.clear()
            self._paint()
        elif isinstance(event, SpanOpened):
            aid = event.agent_id or "?"
            self._opened[event.span_id] = (event.timestamp, aid)
            self._paint()
        elif isinstance(event, SpanClosed):
            opened = self._opened.pop(event.span_id, None)
            if opened is not None:
                opened_at, aid = opened
                delta_s = max(0.0, (event.timestamp - opened_at).total_seconds())
                self._time_by_agent[aid] = self._time_by_agent.get(aid, 0.0) + delta_s
                tok = int(event.token_count or 0)
                self._tok_by_agent[aid] = self._tok_by_agent.get(aid, 0) + tok
            self._paint()
        elif isinstance(event, (RunCompleted, RunFailed)):
            self._paint(footer=True)

    def metrics_snapshot(self) -> tuple[dict[str, float], dict[str, int]]:
        """Return copies of per-agent seconds and token totals (for tests / diagnostics)."""

        return (dict(self._time_by_agent), dict(self._tok_by_agent))

    def _paint(self, *, footer: bool = False) -> None:
        if not self._time_by_agent and not self._tok_by_agent:
            self.update(
                "[italic dim]Per-agent span time and token totals appear after the first run.[/]"
            )
            return
        agents = sorted(set(self._time_by_agent) | set(self._tok_by_agent))
        max_t = max(self._time_by_agent.values()) if self._time_by_agent else 1.0
        max_k = max(self._tok_by_agent.values()) if self._tok_by_agent else 1
        max_t = max_t if max_t > 0 else 1.0
        max_k = max_k if max_k > 0 else 1
        lines: list[str] = []
        bar_w = 22
        for aid in agents:
            t = self._time_by_agent.get(aid, 0.0)
            k = self._tok_by_agent.get(aid, 0)
            tb = _bar_blocks(min(1.0, t / max_t), bar_w, "cyan", "dim")
            kb = _bar_blocks(min(1.0, k / max_k), bar_w, "magenta", "dim")
            lines.append(f"[bold]{aid}[/]")
            lines.append(f"  [dim]time[/] {t:5.2f}s  {tb}")
            lines.append(f"  [dim]tok[/]  {k:5d}   {kb}")
            lines.append("")
        if footer:
            lines.append("[dim]Run finished.[/]")
        self.update("\n".join(lines).rstrip())

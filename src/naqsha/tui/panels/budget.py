"""Budget panel: live ``BudgetProgress`` display from the Typed Event Bus."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from naqsha.core.events import BudgetProgress


class BudgetPanel(Vertical):
    """Shows last budget telemetry for the active run."""

    DEFAULT_CSS = """
    BudgetPanel {
        scrollbar-gutter: stable;
        content-align: left top;
        background: $surface;
        border: round $panel 28%;
        padding: 0 1 1 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._last: BudgetProgress | None = None

    def compose(self) -> ComposeResult:
        yield Static("[dim italic](budget idle)[/]", id="budget-body-static")

    def consume_event(self, event: object) -> None:
        if isinstance(event, BudgetProgress):
            self._last = event
            self._paint()

    def _paint(self) -> None:
        b = self._last
        if b is None:
            return
        wall_pct = (
            100.0 * b.wall_clock_used_seconds / b.wall_clock_limit_seconds
            if b.wall_clock_limit_seconds > 0
            else 0.0
        )
        steps_pct = 100.0 * b.steps_used / b.max_steps if b.max_steps > 0 else 0.0
        tools_pct = (
            100.0 * b.tool_calls_used / b.max_tool_calls if b.max_tool_calls > 0 else 0.0
        )
        txt = (
            f"[bold]{b.agent_id}[/]\n"
            f"[dim]steps[/]  {b.steps_used}/{b.max_steps}  ({steps_pct:.0f}%)\n"
            f"[dim]tools[/]  {b.tool_calls_used}/{b.max_tool_calls}  ({tools_pct:.0f}%)\n"
            f"[dim]wall[/]   {b.wall_clock_used_seconds:.1f}s / {b.wall_clock_limit_seconds:.1f}s  "
            f"({wall_pct:.0f}%)"
        )
        self.query_one("#budget-body-static", Static).update(txt)

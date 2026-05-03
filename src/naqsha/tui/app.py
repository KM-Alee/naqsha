"""Workbench TUI: Core Runtime panels bound to the Typed Event Bus."""

from __future__ import annotations

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header

from naqsha.core.events import RuntimeEvent
from naqsha.core.runtime import CoreRuntime, RunResult
from naqsha.tui.panels.budget import BudgetPanel
from naqsha.tui.panels.chat import ChatPanel
from naqsha.tui.panels.flame import FlamePanel
from naqsha.tui.panels.memory import MemoryBrowserPanel
from naqsha.tui.panels.patch_review import PatchReviewPanel
from naqsha.tui.panels.span_tree import SpanTreePanel
from naqsha.workbench import RuntimeBusReflectionSink


class WorkbenchApp(App[None]):
    """Workbench TUI: core stream, budgets, trace tree, flame, memory, and patch review."""

    CSS_PATH = "workbench.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit", tooltip="Exit the Workbench"),
        Binding("escape", "quit", "Quit", tooltip="Exit the Workbench"),
    ]

    def __init__(self, *, runtime: CoreRuntime, query: str) -> None:
        super().__init__()
        self._runtime = runtime
        self._query = query
        self._last_result: RunResult | None = None
        bus = runtime.config.event_bus
        if bus is None:
            msg = "WorkbenchApp requires RuntimeConfig.event_bus"
            raise ValueError(msg)
        self._bus = bus
        self._patch_sink = RuntimeBusReflectionSink(bus)
        self._workspace = runtime.config.workspace_path.expanduser().resolve()
        self._reflection_parent = self._workspace / ".naqsha" / "reflection-workspaces"

    @property
    def last_result(self) -> RunResult | None:
        return self._last_result

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="workbench-body"):
            with Horizontal(id="main-row"):
                yield ChatPanel(id="chat")
                with Vertical(id="side"):
                    yield BudgetPanel(id="budget")
                    yield SpanTreePanel(id="spans")
            with Horizontal(id="analytics-row"):
                yield FlamePanel(id="flame")
                yield MemoryBrowserPanel(id="memory", workspace_path=self._workspace)
                yield PatchReviewPanel(
                    id="patch",
                    team_workspace=self._workspace,
                    patch_workspace_parent=self._reflection_parent,
                    patch_event_sink=self._patch_sink,
                )
        yield Footer()

    def on_mount(self) -> None:
        self.title = "NAQSHA Workbench"
        q = self._query
        self.sub_title = q if len(q) <= 100 else q[:97] + "…"
        # Distinctive built-in theme; keeps panels readable with $surface / $boost.
        self.theme = "tokyo-night"
        chat = self.query_one(ChatPanel)
        chat.border_title = "Orchestrator"
        self.query_one(BudgetPanel).border_title = "Budget"
        self.query_one(SpanTreePanel).border_title = "Trace tree"
        self.query_one(FlamePanel).border_title = "Time & tokens"
        self.query_one(MemoryBrowserPanel).border_title = "Memory"
        self.query_one(PatchReviewPanel).border_title = "Reflection"
        self._bus.subscribe(self._on_bus_event)
        self.run_tui_agent()

    def _on_bus_event(self, event: RuntimeEvent) -> None:
        self.call_from_thread(self._dispatch_event, event)

    def _dispatch_event(self, event: RuntimeEvent) -> None:
        self.query_one(ChatPanel).consume_event(event)
        self.query_one(BudgetPanel).consume_event(event)
        self.query_one(SpanTreePanel).consume_event(event)
        self.query_one(FlamePanel).consume_event(event)
        self.query_one(MemoryBrowserPanel).consume_event(event)
        self.query_one(PatchReviewPanel).consume_event(event)

    @work(thread=True, exclusive=True)
    def run_tui_agent(self) -> None:
        self._last_result = self._runtime.run(self._query)
        self.call_from_thread(self._run_finished)

    def _run_finished(self) -> None:
        if self._last_result and self._last_result.failed:
            self.notify("Run failed", severity="error", timeout=6)
        else:
            self.notify("Run finished — press q to quit", timeout=6)


def tui_available() -> bool:
    """True when optional ``[tui]`` / dev Textual dependencies are installed."""

    try:
        import textual  # noqa: F401
    except ImportError:
        return False
    else:
        return True


def cli_should_use_tui() -> bool:
    """Interactive terminal check (headless/CI safe)."""

    import os
    import sys

    if os.environ.get("NAQSHA_NO_TUI", "").lower() in ("1", "true", "yes"):
        return False
    return bool(sys.stdin.isatty() and sys.stdout.isatty())


def build_workbench_app(*, runtime: CoreRuntime, query: str) -> WorkbenchApp:
    """Construct a Workbench TUI bound to the given runtime and query."""

    return WorkbenchApp(runtime=runtime, query=query)

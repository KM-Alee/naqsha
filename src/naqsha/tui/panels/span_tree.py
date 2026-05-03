"""Span tree panel: hierarchical spans from ``SpanOpened`` / ``SpanClosed``."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Tree

from naqsha.core.events import SpanClosed, SpanOpened


class SpanTreePanel(Vertical):
    """Expandable span tree grouped by ``agent_id``."""

    DEFAULT_CSS = """
    SpanTreePanel {
        background: $surface;
        border: round $panel 28%;
        padding: 0 0 1 0;
    }
    SpanTreePanel Tree {
        background: transparent;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._by_span: dict[str, Any] = {}
        self._labels: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        yield Tree[str]("Spans", id="span-tree")

    def on_mount(self) -> None:
        tree = self.query_one(Tree[str])
        tree.root.expand()
        tree.show_root = False

    def consume_event(self, event: object) -> None:
        if isinstance(event, SpanOpened):
            self._on_opened(event)
        elif isinstance(event, SpanClosed):
            self._on_closed(event)

    def _on_opened(self, event: SpanOpened) -> None:
        tree = self.query_one(Tree[str])
        aid = event.agent_id or "?"
        short = event.span_id[:8] if len(event.span_id) > 8 else event.span_id
        label = f"[bold]{aid}[/]  [dim]{short}[/]"
        self._labels[event.span_id] = label
        parent_key = event.parent_span_id
        if parent_key and parent_key in self._by_span:
            node = self._by_span[parent_key].add(label, data=event.span_id)
        else:
            node = tree.root.add(label, data=event.span_id)
        self._by_span[event.span_id] = node
        node.expand()

    def _on_closed(self, event: SpanClosed) -> None:
        node = self._by_span.pop(event.span_id, None)
        base = self._labels.pop(event.span_id, None)
        if node is None or base is None:
            return
        tok = event.token_count
        suffix = f" [green]✓[/] [dim]{tok} tok[/]" if tok is not None else " [green]✓[/]"
        node.set_label(base + suffix)

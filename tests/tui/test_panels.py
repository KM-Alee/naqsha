"""Tests for Workbench TUI panels (Textual)."""

from __future__ import annotations

import pytest

pytest.importorskip("textual")

from textual.app import App, ComposeResult
from textual.widgets import Tree

from naqsha.core.events import SpanClosed, SpanOpened, StreamChunkReceived
from naqsha.tui.panels.chat import ChatPanel
from naqsha.tui.panels.span_tree import SpanTreePanel


@pytest.mark.asyncio
async def test_chat_panel_accepts_stream_chunks() -> None:
    class _Harness(App[None]):
        def compose(self) -> ComposeResult:
            yield ChatPanel(id="chat")

    async with _Harness().run_test() as pilot:
        chat = pilot.app.query_one(ChatPanel)
        chat.consume_event(StreamChunkReceived(run_id="r1", agent_id="orch", chunk="hi"))
        await pilot.pause(0.05)
        log = pilot.app.query_one("#chat-log")
        assert log is not None


@pytest.mark.asyncio
async def test_span_tree_nested_spans() -> None:
    class _Harness(App[None]):
        def compose(self) -> ComposeResult:
            yield SpanTreePanel(id="spans")

    async with _Harness().run_test() as pilot:
        panel = pilot.app.query_one(SpanTreePanel)
        panel.consume_event(
            SpanOpened(
                run_id="r",
                trace_id="t",
                span_id="root-span",
                parent_span_id=None,
                agent_id="orch",
            )
        )
        panel.consume_event(
            SpanOpened(
                run_id="r",
                trace_id="t",
                span_id="child-span",
                parent_span_id="root-span",
                agent_id="worker",
            )
        )
        await pilot.pause(0.05)
        tree = pilot.app.query_one(Tree)
        assert len(tree.root.children) == 1
        orch_node = tree.root.children[0]
        assert len(orch_node.children) == 1
        panel.consume_event(
            SpanClosed(
                run_id="r",
                trace_id="t",
                span_id="child-span",
                agent_id="worker",
                token_count=3,
            )
        )
        panel.consume_event(
            SpanClosed(
                run_id="r",
                trace_id="t",
                span_id="root-span",
                agent_id="orch",
            )
        )
        await pilot.pause(0.05)

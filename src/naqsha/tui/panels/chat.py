"""Chat panel: model output and tool activity from Typed Event Bus events."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog

from naqsha.core.events import (
    RunCompleted,
    RunFailed,
    RunStarted,
    StreamChunkReceived,
    ToolCompleted,
    ToolErrored,
    ToolInvoked,
)


class ChatPanel(Vertical):
    """Renders streaming tokens and high-level run activity."""

    DEFAULT_CSS = """
    ChatPanel {
        scrollbar-gutter: stable;
    }
    """

    def compose(self) -> ComposeResult:
        yield RichLog(id="chat-log", highlight=True, markup=True, wrap=True)

    def _log(self) -> RichLog:
        return self.query_one(RichLog)

    def consume_event(self, event: object) -> None:
        log = self._log()
        if isinstance(event, RunStarted):
            q = event.query[:500] + ("…" if len(event.query) > 500 else "")
            log.write(
                f"\n[dim]▸[/] [bold]{event.agent_id}[/]  {event.run_id[:8]}…\n"
                f"[italic dim]{q}[/]"
            )
        elif isinstance(event, StreamChunkReceived):
            log.write(
                f"[green]{event.agent_id}[/]  {event.chunk}",
                scroll_end=True,
            )
        elif isinstance(event, ToolInvoked):
            log.write(f"[dim]•[/] {event.agent_id}  {event.tool_name}")
        elif isinstance(event, ToolCompleted):
            obs = event.observation or ""
            preview = obs[:200] + ("…" if len(obs) > 200 else "")
            log.write(f"  [dim]ok[/] {preview}")
        elif isinstance(event, ToolErrored):
            log.write(
                f"  [red]err[/] {event.tool_name}  {event.error_message[:300]}"
            )
        elif isinstance(event, RunCompleted):
            log.write(
                f"\n[dim]▸[/] [green]done[/]  steps {event.total_steps}"
            )
        elif isinstance(event, RunFailed):
            log.write(f"\n[red]failed[/]  {event.error_message[:400]}")

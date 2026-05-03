"""Reflection Patch review: team vs merge preview; approve/reject via reflection APIs."""

from __future__ import annotations

from pathlib import Path

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Select, Static

from naqsha.core.events import RunStarted
from naqsha.reflection.base import ReflectionPatchEventSink
from naqsha.reflection.loop import (
    approve_patch,
    list_reflection_patch_workspace_ids,
    read_patch_review_texts,
    reject_patch,
)


def _split_side_by_side(left: str, right: str, *, width: int = 42) -> tuple[str, str]:
    la = left.splitlines() or [""]
    lb = right.splitlines() or [""]
    n = max(len(la), len(lb))
    out_l: list[str] = []
    out_r: list[str] = []
    for i in range(n):
        lv = la[i] if i < len(la) else ""
        rv = lb[i] if i < len(lb) else ""
        out_l.append(lv[:width])
        out_r.append(rv[:width])
    return "\n".join(out_l), "\n".join(out_r)


class PatchReviewPanel(Vertical):
    """Side-by-side ``naqsha.toml`` preview; approve/reject use ``reflection.loop``."""

    DEFAULT_CSS = """
    PatchReviewPanel {
        background: $surface;
        border: round $panel 28%;
        padding: 0 1 1 1;
        min-height: 10;
    }
    PatchReviewPanel #patch-hint {
        padding-bottom: 1;
        color: $text-muted;
    }
    PatchReviewPanel Select {
        margin-bottom: 1;
        height: auto;
        background: $boost;
        border: round $panel 35%;
    }
    PatchReviewPanel ScrollableContainer {
        width: 1fr;
        height: 1fr;
        min-height: 5;
        background: $boost;
        border: round $panel 30%;
        margin-right: 1;
    }
    PatchReviewPanel #patch-left, PatchReviewPanel #patch-right {
        padding: 0 1;
        background: transparent;
    }
    PatchReviewPanel #patch-actions {
        height: auto;
        margin-top: 1;
        align: right middle;
    }
    PatchReviewPanel Button {
        margin-left: 1;
    }
    """

    _HINT_OK = "[dim]Pick a patch, then compare team vs merge before approving.[/]"

    def __init__(
        self,
        *,
        team_workspace: Path,
        patch_workspace_parent: Path,
        patch_event_sink: ReflectionPatchEventSink | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._team = team_workspace.expanduser().resolve()
        self._patch_parent = patch_workspace_parent.expanduser().resolve()
        self._patch_sink = patch_event_sink

    def compose(self) -> ComposeResult:
        yield Static(self._HINT_OK, id="patch-hint")
        # Options are ``(label, value)``; ``allow_blank`` uses ``Select.NULL`` when empty.
        yield Select(
            [],
            id="patch-select",
            prompt="Patch workspace",
            allow_blank=True,
            value=Select.NULL,
        )
        with Horizontal(id="patch-diff-row"):
            with ScrollableContainer():
                yield Static("[dim]team[/]", id="patch-left", markup=True)
            with ScrollableContainer():
                yield Static("[dim]merge[/]", id="patch-right", markup=True)
        with Horizontal(id="patch-actions"):
            yield Button("Approve merge", variant="success", id="patch-approve")
            yield Button("Reject", variant="error", id="patch-reject")

    def on_mount(self) -> None:
        self._refresh_options()

    def consume_event(self, event: object) -> None:
        if isinstance(event, RunStarted):
            self._refresh_options()

    def _refresh_options(self) -> None:
        sel = self.query_one("#patch-select", Select)
        ids = list_reflection_patch_workspace_ids(self._patch_parent)
        approve_b = self.query_one("#patch-approve", Button)
        reject_b = self.query_one("#patch-reject", Button)
        if not ids:
            sel.set_options([])
            sel.disabled = True
            approve_b.disabled = True
            reject_b.disabled = True
            self.query_one("#patch-hint", Static).update(
                "[dim]No patches under .naqsha/reflection-workspaces yet.[/]\n"
                "[dim]Run[/] naqsha reflect [dim]after a trace.[/]"
            )
            self._paint_diff("", "")
            return
        self.query_one("#patch-hint", Static).update(self._HINT_OK)
        sel.set_options([(i, i) for i in ids])
        sel.disabled = False
        approve_b.disabled = False
        reject_b.disabled = False
        sel.value = ids[0]
        self._show_diff(str(sel.value))

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "patch-select":
            return
        v = event.value
        if v in (Select.NULL, None):
            self._paint_diff("", "")
            return
        self._show_diff(str(v))

    def _show_diff(self, patch_id: str) -> None:
        if not patch_id:
            self._paint_diff("", "")
            return
        left, right = read_patch_review_texts(
            patch_id,
            team_workspace=self._team,
            workspace_parent=self._patch_parent,
        )
        self._paint_diff(left, right)

    def _paint_diff(self, left: str, right: str) -> None:
        left_w = self.query_one("#patch-left", Static)
        right_w = self.query_one("#patch-right", Static)
        if not left.strip() and not right.strip():
            left_w.update("[italic dim]team naqsha.toml[/]")
            right_w.update("[italic dim]proposed merge/naqsha.toml[/]")
            return
        ltxt, rtxt = _split_side_by_side(left, right)
        left_w.update(f"[bold]team[/]\n[dim]{escape(ltxt)}[/]")
        right_w.update(f"[bold]merge[/]\n[dim]{escape(rtxt)}[/]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        sel = self.query_one("#patch-select", Select)
        if sel.disabled or sel.selection is None:
            return
        pid = str(sel.selection)
        if event.button.id == "patch-approve":
            approve_patch(
                pid,
                team_workspace=self._team,
                workspace_parent=self._patch_parent,
                patch_event_sink=self._patch_sink,
            )
            self.app.notify("Patch merged — boot verification runs on next run.", timeout=8)
        elif event.button.id == "patch-reject":
            reject_patch(pid, workspace_parent=self._patch_parent)
            self.app.notify("Patch rejected (marker written).", timeout=6)

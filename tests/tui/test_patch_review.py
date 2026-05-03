"""Patch review panel tests."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("textual")

from textual.app import App, ComposeResult
from textual.widgets import Button, Select

from naqsha.tui.panels.patch_review import PatchReviewPanel


@pytest.mark.asyncio
async def test_patch_review_mounts_when_no_patch_dirs(tmp_path: Path) -> None:
    """Regression: empty patch list must not assign an illegal Select value (Textual)."""
    team = tmp_path / "team"
    team.mkdir()
    parent = tmp_path / "patches"
    parent.mkdir()

    class _Harness(App[None]):
        def compose(self) -> ComposeResult:
            yield PatchReviewPanel(
                id="patch",
                team_workspace=team,
                patch_workspace_parent=parent,
                patch_event_sink=None,
            )

    async with _Harness().run_test() as pilot:
        sel = pilot.app.query_one(Select)
        assert sel.disabled is True
        assert sel.selection is None


@pytest.mark.asyncio
async def test_patch_review_approve_invokes_callback(tmp_path: Path) -> None:
    team = tmp_path / "team"
    team.mkdir()
    (team / "naqsha.toml").write_text("orig=1\n", encoding="utf-8")
    parent = tmp_path / "patches"
    parent.mkdir()
    pid = "reflection-patch-test1234"
    pws = parent / pid
    pws.mkdir()
    merge = pws / "merge"
    merge.mkdir()
    (merge / "naqsha.toml").write_text("orig=1\n#patch\n", encoding="utf-8")

    called: list[str] = []

    class _Panel(PatchReviewPanel):
        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "patch-approve":
                called.append("approve")
                return
            super().on_button_pressed(event)

    class _Harness(App[None]):
        def compose(self) -> ComposeResult:
            yield _Panel(
                id="patch",
                team_workspace=team,
                patch_workspace_parent=parent,
                patch_event_sink=None,
            )

    async with _Harness().run_test() as pilot:
        sel = pilot.app.query_one(Select)
        assert str(sel.value) == pid
        await pilot.click("#patch-approve")
        await pilot.pause(0.08)

    assert called == ["approve"]

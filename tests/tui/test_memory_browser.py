"""Memory browser panel tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("textual")

from textual.app import App, ComposeResult

from naqsha.core.events import RunStarted
from naqsha.tui.panels.memory import MemoryBrowserPanel


@pytest.mark.asyncio
async def test_memory_browser_lists_tables_and_rows(tmp_path: Path) -> None:
    db = tmp_path / "memory.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE shared_notes (id INTEGER PRIMARY KEY, body TEXT)")
    con.execute("INSERT INTO shared_notes (body) VALUES ('a'), ('b')")
    con.commit()
    con.close()

    class _Harness(App[None]):
        def compose(self) -> ComposeResult:
            yield MemoryBrowserPanel(id="mem", workspace_path=tmp_path, db_path=db)

    async with _Harness().run_test() as pilot:
        panel = pilot.app.query_one(MemoryBrowserPanel)
        panel.consume_event(RunStarted(run_id="r", agent_id="a", query="q"))
        await pilot.pause(0.08)
        from textual.widgets import DataTable, OptionList

        ol = pilot.app.query_one(OptionList)
        assert ol.option_count >= 1
        prompts = [str(o.prompt) for o in ol.options]
        assert any("shared_notes" in p for p in prompts)
        dt = pilot.app.query_one(DataTable)
        assert dt.row_count == 2

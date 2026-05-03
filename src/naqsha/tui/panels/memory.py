"""Memory browser panel: SQLite table list and first rows from the team memory DB."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, OptionList, Static
from textual.widgets.option_list import Option

from naqsha.core.events import RunStarted


class MemoryBrowserPanel(Vertical):
    """Browse ``shared_`` / ``private_`` tables in the workspace Dynamic Memory Engine DB."""

    DEFAULT_CSS = """
    MemoryBrowserPanel {
        background: $surface;
        border: round $panel 28%;
        padding: 0 1 1 1;
        min-height: 10;
    }
    MemoryBrowserPanel #memory-hint {
        padding-bottom: 1;
        color: $text-muted;
    }
    MemoryBrowserPanel OptionList {
        width: 1fr;
        max-width: 36;
        height: 1fr;
        min-height: 6;
        background: $boost;
        border: round $panel 32%;
    }
    MemoryBrowserPanel DataTable {
        height: 1fr;
        min-height: 6;
        background: $boost;
        border: round $panel 32%;
    }
    """

    def __init__(self, *, workspace_path: Path, db_path: Path | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._workspace = workspace_path.expanduser().resolve()
        self._db = db_path
        self._selected_table: str | None = None

    def compose(self) -> ComposeResult:
        yield Static("", id="memory-hint")
        with Horizontal(id="memory-split"):
            yield OptionList(id="memory-tables")
            yield DataTable(id="memory-grid", show_header=True, zebra_stripes=True)

    def on_mount(self) -> None:
        self._refresh_db_path_label()
        self._load_tables()

    def consume_event(self, event: object) -> None:
        if isinstance(event, RunStarted):
            self._refresh_db_path_label()
            self._load_tables()

    def _resolve_db(self) -> Path | None:
        if self._db is not None:
            p = self._db.expanduser().resolve()
            return p if p.is_file() else None
        candidate = self._workspace / ".naqsha" / "memory.db"
        return candidate if candidate.is_file() else None

    def _refresh_db_path_label(self) -> None:
        hint = self.query_one("#memory-hint", Static)
        p = self._resolve_db()
        if p is None:
            hint.update(
                "[dim]No DB yet at[/] .naqsha/memory.db  [dim](creates on first memory use)[/]"
            )
            return
        try:
            rel = p.relative_to(self._workspace)
            disp = str(rel)
        except ValueError:
            disp = p.name
        hint.update(f"[dim]DB[/] {disp}")

    def _load_tables(self) -> None:
        ol = self.query_one("#memory-tables", OptionList)
        ol.clear_options()
        p = self._resolve_db()
        if p is None:
            self._selected_table = None
            self._clear_grid()
            return
        try:
            con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        except sqlite3.Error:
            self._selected_table = None
            self._clear_grid()
            return
        try:
            cur = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
            names = [r[0] for r in cur.fetchall() if r[0]]
        finally:
            con.close()
        for n in names:
            ol.add_option(Option(n))
        if names:
            ol.highlighted = 0
            self._selected_table = str(names[0])
            self._load_rows_for_selected()
        else:
            self._selected_table = None
            self._clear_grid()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != "memory-tables":
            return
        self._selected_table = str(event.option.prompt)
        self._load_rows_for_selected()

    def _clear_grid(self) -> None:
        dt = self.query_one("#memory-grid", DataTable)
        dt.clear(columns=True)

    def _load_rows_for_selected(self) -> None:
        dt = self.query_one("#memory-grid", DataTable)
        dt.clear(columns=True)
        p = self._resolve_db()
        table = self._selected_table
        if p is None or not table:
            return
        con: sqlite3.Connection | None = None
        try:
            con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            cur = con.execute(f'SELECT * FROM "{table}" LIMIT 50')
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
        except sqlite3.Error:
            return
        finally:
            if con is not None:
                con.close()
        if not cols:
            return
        for c in cols:
            dt.add_column(c, key=c)
        for r in rows:
            dt.add_row(*[str(x) if x is not None else "" for x in r])
        dt.cursor_type = "row"

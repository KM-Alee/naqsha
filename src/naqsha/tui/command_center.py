"""Interactive Command Center (Team Workspace dashboard + orchestrator prompts)."""

from __future__ import annotations

import json
import os
import re
import shutil
import tomllib
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, Static, TextArea

from naqsha.core.event_bus import RuntimeEventBus
from naqsha.core.events import CircuitBreakerTripped as BusCircuitBreakerTripped
from naqsha.core.events import RunCompleted as BusRunCompleted
from naqsha.core.events import RunFailed as BusRunFailed
from naqsha.core.events import RunStarted as BusRunStarted
from naqsha.core.events import ToolCompleted as BusToolCompleted
from naqsha.core.events import ToolErrored as BusToolErrored
from naqsha.models.trace_replay import TraceReplayExhausted
from naqsha.orchestration.team_runtime import (
    build_team_workspace_runtime,
    run_profile_for_topology_agent,
)
from naqsha.orchestration.topology import parse_team_topology, parse_team_topology_file
from naqsha.profiles import ProfileValidationError
from naqsha.replay import (
    TraceReplayError,
    compare_replay,
    first_query_from_trace,
    summarize_trace,
)
from naqsha.scheduler import ReplayObservationMissing
from naqsha.trace.jsonl import JsonlTraceStore
from naqsha.trace_scan import latest_run_id, list_run_ids_by_recency
from naqsha.tui.panels.budget import BudgetPanel
from naqsha.tui.panels.chat import ChatPanel
from naqsha.tui.panels.flame import FlamePanel
from naqsha.tui.panels.memory import MemoryBrowserPanel
from naqsha.tui.panels.patch_review import PatchReviewPanel
from naqsha.tui.panels.span_tree import SpanTreePanel
from naqsha.tui.session import append_error_log, load_session, save_session
from naqsha.wiring import build_trace_replay_runtime
from naqsha.workbench import RuntimeBusReflectionSink


def _health_messages(project: Path) -> list[str]:
    msgs: list[str] = []
    tom = project / "naqsha.toml"
    if not tom.is_file():
        msgs.append("`naqsha.toml` is missing.")
        return msgs
    try:
        topo = parse_team_topology_file(tom)
    except ProfileValidationError as exc:
        msgs.append(str(exc))
        return msgs

    orch = topo.workspace.orchestrator
    if orch not in topo.agents:
        msgs.append("Orchestrator id is missing from [agents].")
    trace_dir = topo.workspace.resolve_trace_dir(project)
    try:
        trace_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        msgs.append(f"Trace directory unusable ({trace_dir}): {exc}")
    resolved = topo.memory.resolve_paths(project)
    if resolved.type != "sqlite":
        msgs.append(f"Memory type must be sqlite; got {resolved.type!r}.")
    else:
        dbdir = resolved.db_path.parent
        try:
            dbdir.mkdir(parents=True, exist_ok=True)
            _ = resolved.db_path
        except OSError as exc:
            msgs.append(f"Memory DB path parent not writable ({dbdir}): {exc}")

    for aid, cfg in topo.agents.items():
        envname: str | None = None
        if cfg.model_adapter == "openai_compat" and cfg.openai_compat:
            envname = str(cfg.openai_compat.get("api_key_env", "OPENAI_API_KEY"))
        elif cfg.model_adapter == "anthropic" and cfg.anthropic:
            envname = str(cfg.anthropic.get("api_key_env", "ANTHROPIC_API_KEY"))
        elif cfg.model_adapter == "gemini" and cfg.gemini:
            envname = str(cfg.gemini.get("api_key_env", "GEMINI_API_KEY"))
        elif cfg.model_adapter == "ollama" and cfg.ollama:
            raw_ev = cfg.ollama.get("api_key_env")
            envname = str(raw_ev).strip() if isinstance(raw_ev, str) and raw_ev.strip() else None

        if envname and cfg.model_adapter != "fake" and not os.environ.get(envname):
            msgs.append(f"Agent {aid!r}: environment variable {envname!r} is not set.")

    if not msgs:
        msgs.append("Workspace configuration looks usable.")
    return msgs


_SQL_START = re.compile(
    r"^\s*(select|insert\s+into|update|delete\s+from)\b",
    re.IGNORECASE | re.DOTALL,
)


def _strip_sql_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql).strip()


def _validate_memory_sql_tables(sql: str, orch_id: str) -> tuple[bool, str]:
    orch = orch_id.lower()
    for m in re.finditer(r'"([^"]+)"', sql):
        t = m.group(1).lower()
        if t.startswith("sqlite_"):
            continue
        if not (
            t.startswith("shared_")
            or t.startswith(f"private_{orch}_")
            or not t.startswith("private_")
        ):
            if t.startswith("private_"):
                return False, f'Table "{m.group(1)}" belongs to another agent.'
    norm = sql.lower()
    pat = orch.replace("\\", "").lower()
    for bare in re.findall(r"\b(from|into|update)\s+([a-z0-9_]+)", norm, flags=re.I):
        t = bare[1].strip('"').lower()
        if t.startswith("sqlite_"):
            continue
        if not (t.startswith("shared_") or t.startswith(f"private_{pat}_")):
            if t.startswith("private_"):
                return False, f'Table `{bare[1]}` is outside orchestrator-visible memory.'
    return True, ""


def _run_memory_sql(
    db_path: Path, sql_raw: str, orch_id: str
) -> tuple[bool, str]:
    body = _strip_sql_comments(sql_raw)
    if body.count(";") > 1:
        return False, "Use only one SQL statement."
    stmt = body.rstrip().rstrip(";").strip()
    if not stmt:
        return False, "Empty SQL."
    if not _SQL_START.match(stmt):
        return False, "Only SELECT, INSERT, UPDATE, DELETE are allowed."
    ok_tbl, tbl_err = _validate_memory_sql_tables(stmt, orch_id)
    if not ok_tbl:
        return False, tbl_err
    import sqlite3

    try:
        con = sqlite3.connect(str(db_path))
        try:
            cur = con.execute(stmt)
            if stmt.strip().upper().startswith("SELECT"):
                rows = cur.fetchall()
                hdr = [d[0] for d in (cur.description or [])]
                return True, f"{hdr}\n" + "\n".join(str(r) for r in rows[:200])
            con.commit()
            msg = (
                f"OK ({cur.rowcount} rows affected)."
                if hasattr(cur, "rowcount")
                else "OK."
            )
            return True, msg
        finally:
            con.close()
    except sqlite3.Error as exc:
        return False, str(exc)


class _TomlEditorScreen(ModalScreen[str | None]):
    BINDINGS = [
        Binding("escape", "cancel", "", tooltip="Cancel editing and close"),
        Binding("ctrl+s", "save", "", tooltip="Save changes to naqsha.toml"),
    ]

    def __init__(self, *, initial_text: str) -> None:
        super().__init__()
        self._initial = initial_text

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold #ebdbb2]Edit Configuration[/]")
            yield Label("[#a89984]Press Ctrl+S to save, Esc to cancel[/]")
            yield TextArea(self._initial, id="modal-editor", language="toml")
            with Horizontal(id="modal-footer"):
                yield Button("Save Changes", variant="primary", id="save-toml-btn")
                yield Button("Cancel", id="cancel-toml-btn")

    def action_save(self) -> None:
        self._do_save()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-toml-btn":
            self._do_save()
        elif event.button.id == "cancel-toml-btn":
            self.dismiss(None)

    def _do_save(self) -> None:
        ta = self.query_one("#modal-editor", TextArea)
        self.dismiss(str(ta.text))



class _TracePickerScreen(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "dismiss", "", tooltip="Close trace picker")]

    def __init__(self, *, traces: tuple[str, ...]) -> None:
        super().__init__()
        self._traces = traces

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold #ebdbb2]Select Trace[/]")
            yield Label("[#a89984]Type run_id stem and press Enter[/]")
            yield Input(placeholder="run_id (.jsonl stem)", id="trace-pick-input")
            yield Static("\n".join(self._traces[:40]), id="trace-list-preview")
            with Horizontal():
                yield Button("Cancel", id="pick-cancel")

    def action_dismiss(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "trace-pick-input":
            stem = event.value.strip()
            if stem:
                self.dismiss(stem)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "pick-cancel":
            self.dismiss(None)


class _SqlScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape", "dismiss", "", tooltip="Close SQL console")]

    def __init__(self, *, db_path: Path, orch_id: str) -> None:
        super().__init__()
        self._db_path = db_path
        self._orch = orch_id

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold #ebdbb2]Memory SQL Console[/]")
            yield Label(
                f"[#a89984]Orchestrator: [#83a598]{self._orch}[/][/]\n"
                f"[#a89984]Access: shared_* and private_{self._orch}_*[/]"
            )
            yield TextArea(
                'SELECT * FROM "shared_example" LIMIT 5;',
                id="modal-sql",
                language="sql",
            )
            yield Static("", id="sql-result")
            with Horizontal():
                yield Button("Run Query", variant="primary", id="sql-run")
                yield Button("Close", id="sql-close")

    def action_dismiss(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "sql-close":
            self.dismiss()
        elif event.button.id == "sql-run":
            sql = str(self.query_one("#modal-sql", TextArea).text)
            ok, out = _run_memory_sql(self._db_path, sql, self._orch)
            sev = "red" if not ok else "green"
            self.query_one("#sql-result", Static).update(f"[{sev}]{out}[/]")


class _ReadonlyTextModal(ModalScreen[None]):
    BINDINGS = [Binding("escape", "dismiss", "", tooltip="Close this view")]

    def __init__(self, *, caption: str, body: str) -> None:
        super().__init__()
        self._cap = caption
        self._body = body

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._cap)
            yield TextArea(self._body, read_only=True, id="ro-text", language=None)
            yield Button("Close", id="ro-close")

    def action_dismiss(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ro-close":
            self.dismiss()


class _ProfileScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape", "dismiss", "", tooltip="Close profile manager")]

    root: Path

    def __init__(self, *, workspace: Path, names: tuple[str, ...]) -> None:
        super().__init__()
        self.root = workspace
        self._names = names

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold #ebdbb2]Profiles Manager[/]")
            yield Label(f"[#a89984]Location: {self.root}/.naqsha/profiles/[/]")
            yield Label("[#a89984]Available Profiles:[/]")
            yield Static(
                "\n".join(self._names)
                if self._names
                else "[#665c54](no profiles found)[/]",
                id="profile-list-static",
            )
            yield Label("[#a89984]Create New Profile:[/]")
            yield Input(placeholder="Enter new profile name", id="new-profile-name")
            with Horizontal():
                yield Button("Duplicate First Profile", id="dup-profile", variant="primary")
                yield Button("Refresh List", id="profile-refresh")
                yield Button("Close", id="profile-close")

    def action_dismiss(self) -> None:
        self.dismiss()

    def _profiles_dir(self) -> Path:
        d = self.root / ".naqsha" / "profiles"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def on_button_pressed(self, event: Button.Pressed) -> None:
        pd = self._profiles_dir()
        if event.button.id == "profile-refresh":
            names = tuple(sorted(p.stem for p in pd.glob("*.json")))
            self.query_one("#profile-list-static", Static).update(
                "\n".join(names) or "[#665c54](no profiles found)[/]"
            )
        elif event.button.id == "dup-profile":
            name_in = self.query_one("#new-profile-name", Input).value.strip() or "copy"
            srcs = sorted(pd.glob("*.json"))
            if not srcs:
                return
            dest = pd / f"{name_in}.json"
            shutil.copy2(srcs[0], dest)
            names = tuple(sorted(p.stem for p in pd.glob("*.json")))
            self.query_one("#profile-list-static", Static).update("\n".join(names))
            self.query_one("#new-profile-name", Input).value = ""
        elif event.button.id == "profile-close":
            self.dismiss()


class CommandCenterApp(App[None]):
    """Team Workspace dashboard: orchestrator chat, telemetry, tooling modals."""

    CSS_PATH = "command_center.tcss"
    BINDINGS = [
        Binding("ctrl+q", "quit_safe", "Quit", tooltip="Exit the Command Center"),
        Binding("escape", "pop_or_nop", ""),
        Binding(
            "ctrl+c",
            "request_interrupt",
            "Interrupt",
            tooltip="Stop the current agent run",
        ),
        Binding(
            "ctrl+r",
            "replay_latest",
            "Replay",
            tooltip="Replay the most recent trace for comparison",
        ),
        Binding(
            "ctrl+m",
            "memory_sql_modal",
            "Memory SQL",
            tooltip="Open SQL console for memory queries",
        ),
        Binding(
            "ctrl+p",
            "focus_patch",
            "Patches",
            tooltip="Jump to the Reflection Patches panel",
        ),
        Binding(
            "ctrl+t",
            "pick_trace_modal",
            "Traces",
            tooltip="Browse and inspect saved trace files",
        ),
        Binding(
            "ctrl+s",
            "edit_toml_modal",
            "Config",
            tooltip="Edit naqsha.toml workspace configuration",
        ),
        Binding(
            "shift+p", "pause_run", "Pause", tooltip="Pause the current agent run"
        ),
        Binding(
            "shift+u", "resume_run", "Resume", tooltip="Resume a paused agent run"
        ),
        Binding(
            "ctrl+g",
            "profile_modal",
            "Profiles",
            tooltip="Manage agent profiles in .naqsha/profiles/",
        ),
        Binding(
            "ctrl+h",
            "health_modal",
            "Health",
            tooltip="Run workspace health check diagnostics",
        ),
        Binding(
            "ctrl+e",
            "export_metrics",
            "Export metrics",
            tooltip="Export session metrics to .naqsha/metrics-*.json",
        ),
        Binding(
            "f1",
            "copy_last_error_hint",
            "",
            tooltip="Copy the most recent error to clipboard",
        ),
    ]

    def __init__(self, *, workspace_root: Path) -> None:
        super().__init__()
        self._cwd = workspace_root.expanduser().resolve()
        self._bus = RuntimeEventBus()
        self._topology = parse_team_topology_file(self._cwd / "naqsha.toml")
        self._patch_sink = RuntimeBusReflectionSink(self._bus)
        self._reflection_parent = self._cwd / ".naqsha" / "reflection-workspaces"
        self._runtime_ref_holder: dict[str, Any] = {"rt": None}
        self._last_run_id: str | None = None
        self._session = load_session(self._cwd)
        self._errors_ring: list[str] = []
        self._breaker_tripped_seen = False
        self._tool_calls_seen = 0
        self._policy_denials = 0

    def compose(self) -> ComposeResult:
        desc = self._topology.workspace.description
        title = self._topology.workspace.name + (f" — {desc}" if desc else "")
        self.title = title
        yield Header()
        with Vertical(id="cc-body"):
            yield Static("", id="cc-run-metrics")
            with Horizontal(id="main-row-cc"):
                with Vertical(id="cc-chat-container"):
                    yield ChatPanel(id="chat-cc")
                    with Horizontal(id="cc-query-row"):
                        yield Input(placeholder="Ask the orchestrator…", id="query-input-cc")
                with Vertical(id="side-cc"):
                    yield Static("", id="jobs-panel")
                    yield BudgetPanel(id="budget-cc")
                    yield SpanTreePanel(id="spans-cc")
            with Horizontal(id="analytics-row-cc"):
                yield FlamePanel(id="flame-cc")
                yield MemoryBrowserPanel(id="memory-cc", workspace_path=self._cwd)
                yield PatchReviewPanel(
                    id="patch-cc",
                    team_workspace=self._cwd,
                    patch_workspace_parent=self._reflection_parent,
                    patch_event_sink=self._patch_sink,
                )
        yield Footer()

    def on_mount(self) -> None:
        self.theme = "gruvbox"
        inp = self.query_one("#query-input-cc", Input)
        inp.value = self._session.last_query
        inp.focus()

        self.sub_title = (
            "^Q Quit · ^C Interrupt · ^R Replay · ^T Traces · ^S Config · ^G Profiles · "
            "^H Health · ^M Memory · ^P Patches · ^E Export · ⇧P/U Pause/Resume · "
            "tools auto-approved in this UI"
        )

        cp = self.query_one("#jobs-panel", Static)
        cp.update("[#665c54]Idle[/]  [#83a598]→[/]  Submit a prompt to start a run")

        chat = self.query_one("#chat-cc", ChatPanel)
        chat.border_title = "Orchestrator Chat"
        self.query_one("#budget-cc", BudgetPanel).border_title = "Budget & Limits"
        self.query_one("#spans-cc", SpanTreePanel).border_title = "Trace Tree"
        self.query_one("#flame-cc", FlamePanel).border_title = "Time & Tokens"
        self.query_one("#memory-cc", MemoryBrowserPanel).border_title = "Memory Browser"
        self.query_one("#patch-cc", PatchReviewPanel).border_title = "Reflection Patches"

        self._bus.subscribe(self._on_bus_any)
        self._refresh_health_strip()

    def _on_bus_any(self, ev: object) -> None:
        self.call_from_thread(self._consume_bus, ev)

    def _consume_bus(self, ev: object) -> None:
        chat = self.query_one("#chat-cc", ChatPanel)
        bud = self.query_one("#budget-cc", BudgetPanel)
        sp = self.query_one("#spans-cc", SpanTreePanel)
        fl = self.query_one("#flame-cc", FlamePanel)
        mem = self.query_one("#memory-cc", MemoryBrowserPanel)
        pr = self.query_one("#patch-cc", PatchReviewPanel)

        chat.consume_event(ev)
        bud.consume_event(ev)
        sp.consume_event(ev)
        fl.consume_event(ev)
        mem.consume_event(ev)
        pr.consume_event(ev)

        if isinstance(ev, BusToolCompleted | BusToolErrored):
            self._refresh_health_strip()

        if isinstance(ev, BusToolErrored):
            err_line = getattr(ev, "error_message", str(ev))
            if "policy" in err_line.lower() or "approval" in err_line.lower():
                self._policy_denials += 1
            append_error_log(
                self._cwd, f"[{datetime.now(tz=UTC).isoformat()}] ToolErrored: {err_line}"
            )
            self._errors_ring.append(err_line[:240])
            if len(self._errors_ring) > 12:
                self._errors_ring.pop(0)

        if isinstance(ev, BusToolCompleted):
            self._tool_calls_seen += 1

        if isinstance(ev, BusCircuitBreakerTripped):
            self._breaker_tripped_seen = True

        jp = self.query_one("#jobs-panel", Static)
        trace_dir = self._topology.workspace.resolve_trace_dir(self._cwd)
        ids = list_run_ids_by_recency(trace_dir)
        ids_preview = ", ".join(ids[:5]) if ids else ""

        if isinstance(ev, BusRunStarted):
            self._last_run_id = ev.run_id
            tail = f"[#a89984]{ids_preview}[/]" if ids_preview else "[#665c54](no prior traces)[/]"
            jp.update(
                f"[bold #b8bb26]RUNNING[/] [bold #ebdbb2]{ev.run_id[:8]}[/]  "
                f"[#665c54]│[/]  [#83a598]{ev.agent_id}[/]\n{tail}"
            )
        elif isinstance(ev, BusRunCompleted):
            self._last_run_id = ev.run_id
            jp.update(
                f"[bold #b8bb26]COMPLETED[/] [bold #ebdbb2]{ev.run_id[:8]}[/]  "
                "[#665c54]→ see budget panel[/]"
            )
            self.notify("Run completed", timeout=5)
        elif isinstance(ev, BusRunFailed):
            jp.update(f"[bold #fb4934]FAILED[/] [bold #ebdbb2]{ev.run_id[:8]}[/]")
            msg = getattr(ev, "error_message", "failed")[:420]
            self.notify(f"run failed — {msg}", severity="error", timeout=14)
            append_error_log(
                self._cwd,
                f"[{datetime.now(tz=UTC).isoformat()}] RUN_FAILED run={ev.run_id} {msg}",
            )

    def _refresh_health_strip(self) -> None:
        strip = self.query_one("#cc-run-metrics", Static)
        name = self._topology.workspace.name
        orch = self._topology.workspace.orchestrator
        brk = "[#fb4934]TRIPPED[/]" if self._breaker_tripped_seen else "[#b8bb26]OK[/]"
        strip.update(
            f"[bold #83a598]{name}[/]  [#665c54]│[/]  Orchestrator: [#fabd2f]{orch}[/]  "
            f"[#665c54]│[/]  Tools: [#b8bb26]{self._tool_calls_seen}[/]  "
            f"[#665c54]│[/]  Denials: [#fb4934]{self._policy_denials}[/]  "
            f"[#665c54]│[/]  Breaker: {brk}"
        )

    def action_pop_or_nop(self) -> None:
        if len(self.screen_stack) > 1:
            self.pop_screen()

    def action_quit_safe(self) -> None:
        self._persist_session_quick()
        self.exit()

    def on_unmount(self) -> None:
        self._persist_session_quick()

    def _persist_session_quick(self) -> None:
        # last_query synced in on_input_changed; querying #query-input-cc fails after teardown.
        save_session(self._cwd, self._session)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "query-input-cc":
            self._session.last_query = event.value

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "query-input-cc":
            q = event.value.strip()
            if not q:
                return
            self._persist_session_quick()
            self.run_orchestrator_query(q)

    @work(thread=True, exclusive=True, name="cmd_center_run")
    def run_orchestrator_query(self, query: str) -> None:
        bus = self._bus
        rt = build_team_workspace_runtime(
            self._cwd,
            event_bus=bus,
            approve_prompt=False,
            implicit_tool_approval=True,
        )
        self._runtime_ref_holder["rt"] = rt
        try:
            res = rt.run(query)
            if res.failed:
                self.call_from_thread(
                    lambda: self.notify("Run ended with failure", severity="warning", timeout=8)
                )
        except Exception as exc:
            append_error_log(
                self._cwd,
                f"[{datetime.now(tz=UTC).isoformat()}] UNHANDLED_RUNTIME_EXC: {exc}",
            )

    # --- Toolbar actions -------------------------------------------------

    def action_request_interrupt(self) -> None:
        rt = self._runtime_ref_holder.get("rt")
        if rt is None:
            return
        rt.request_interrupt()

    def action_pause_run(self) -> None:
        rt = self._runtime_ref_holder.get("rt")
        if rt is None:
            return
        rt.request_pause()
        self.notify("Pause requested")

    def action_resume_run(self) -> None:
        rt = self._runtime_ref_holder.get("rt")
        if rt is None:
            return
        rt.request_resume()

    @work(exclusive=True)
    async def action_replay_latest(self) -> None:
        rid = self._last_run_id
        td = self._topology.workspace.resolve_trace_dir(self._cwd)
        store = JsonlTraceStore(td)
        if not rid:
            rid = latest_run_id(td) or ""

        reference = rid and store.load(rid)
        if not reference:
            self.notify("No traces to replay", severity="error")
            return
        orch_cfg = self._topology.agents[self._topology.workspace.orchestrator]
        profile = run_profile_for_topology_agent(
            orch_cfg,
            workspace=self._topology.workspace,
            trace_dir=td,
            tool_root=self._cwd,
            base_dir=self._cwd,
        )
        try:
            q = first_query_from_trace(reference)
            runtime = build_trace_replay_runtime(profile, reference)
            replay_result = runtime.run(q)
            replay_ev = store.load(replay_result.run_id)
            diff = compare_replay(reference, replay_ev if replay_ev else [])
            body = json.dumps(asdict(diff), indent=2, sort_keys=True, default=str)
            self.push_screen(
                _ReadonlyTextModal(caption="Replay comparison vs reference trace", body=body)
            )
        except (TraceReplayError, TraceReplayExhausted, ReplayObservationMissing) as exc:
            append_error_log(self._cwd, f"replay_failed: {exc}")
            self.notify(f"replay error: {exc}", severity="error")

    @work(exclusive=True)
    async def action_memory_sql_modal(self) -> None:
        resolved = self._topology.memory.resolve_paths(self._cwd)
        if not resolved.db_path.parent.exists():
            try:
                resolved.db_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        orch_id = self._topology.workspace.orchestrator
        self.push_screen(_SqlScreen(db_path=resolved.db_path, orch_id=orch_id))

    @work(exclusive=True)
    async def action_focus_patch(self) -> None:
        self.query_one("#patch-cc", PatchReviewPanel).focus()

    @work(exclusive=True)
    async def action_pick_trace_modal(self) -> None:
        td = self._topology.workspace.resolve_trace_dir(self._cwd)
        ids = tuple(list_run_ids_by_recency(td)[:120])
        store = JsonlTraceStore(td)
        out = await self.push_screen_wait(_TracePickerScreen(traces=ids))
        if not out:
            return
        summary = summarize_trace(store, out)
        blob = json.dumps(asdict(summary), indent=2, sort_keys=True, default=str)
        self.push_screen(_ReadonlyTextModal(caption=f"Trace [bold]{out}[/]", body=blob))

    @work(exclusive=True)
    async def action_edit_toml_modal(self) -> None:
        path = self._cwd / "naqsha.toml"
        txt = path.read_text(encoding="utf-8") if path.is_file() else ""
        edited = await self.push_screen_wait(_TomlEditorScreen(initial_text=txt))
        if edited is None:
            return
        try:
            data = tomllib.loads(edited)
            parse_team_topology(data, base_dir=self._cwd)
            path.write_text(edited, encoding="utf-8")
            self._topology = parse_team_topology_file(path)
            self.notify("Saved naqsha.toml · reload applies to future runs.")
        except (
            ProfileValidationError,
            OSError,
            ValueError,
            TypeError,
            UnicodeDecodeError,
            tomllib.TOMLDecodeError,
        ) as exc:
            self.notify(str(exc), severity="error", timeout=12)
            append_error_log(self._cwd, f"config_validation_failed: {exc}")

    @work(exclusive=True)
    async def action_health_modal(self) -> None:
        msgs = _health_messages(self._cwd)
        self.push_screen(
            _ReadonlyTextModal(caption="Workspace health check", body="\n".join(msgs))
        )

    @work(exclusive=True)
    async def action_profile_modal(self) -> None:
        pd = self._cwd / ".naqsha" / "profiles"
        names = tuple(sorted(p.stem for p in pd.glob("*.json")))
        await self.push_screen_wait(_ProfileScreen(workspace=self._cwd, names=names))

    @work(exclusive=True)
    async def action_export_metrics(self) -> None:
        times, tokens = self.query_one("#flame-cc", FlamePanel).metrics_snapshot()
        orch = self._topology.workspace.orchestrator
        payload = {
            "exported_at": datetime.now(tz=UTC).isoformat(),
            "breaker_tripped_seen": self._breaker_tripped_seen,
            "tool_calls_session": self._tool_calls_seen,
            "approval_denials_session": self._policy_denials,
            "wall_seconds_per_agent": times,
            "tokens_per_agent": tokens,
            "orchestrator": orch,
        }
        ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        out = self._cwd / ".naqsha" / f"metrics-{ts}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.notify(f"Wrote metrics to {out.name}")

    def action_copy_last_error_hint(self) -> None:
        if not self._errors_ring:
            self.notify("(no cached errors)")
            return
        try:
            self.copy_to_clipboard(self._errors_ring[-1])  # type: ignore[attr-defined]
        except Exception:
            self.notify("Clipboard unavailable")


def run_command_center(*, cwd: Path) -> None:
    """Launch the interactive Command Center (expects ``cwd/naqsha.toml``)."""

    CommandCenterApp(workspace_root=cwd.expanduser().resolve()).run()

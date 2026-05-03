"""Interactive ``naqsha init`` wizard (Workbench TUI)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Checkbox, Footer, Header, Input, Label, Select, Static

from naqsha.core.budgets import BudgetLimits
from naqsha.orchestration.topology import (
    MEMORY_DECORATED_TOOL_NAMES,
    parse_team_topology,
)
from naqsha.project import init_agent_project
from naqsha.tools.base import RiskTier
from naqsha.tools.starter import starter_tool_names

_DEF_BUDGET = BudgetLimits()

POWER_ORCH_BUDGET = BudgetLimits(
    max_steps=96,
    max_tool_calls=192,
    wall_clock_seconds=7200.0,
    per_tool_seconds=180.0,
)
POWER_WORKER_BUDGET = BudgetLimits(
    max_steps=64,
    max_tool_calls=160,
    wall_clock_seconds=5400.0,
    per_tool_seconds=120.0,
)


def _sorted_power_tools() -> list[str]:
    return sorted(starter_tool_names() | MEMORY_DECORATED_TOOL_NAMES)


def _escape_toml_str(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _parse_workspace_tiers(text: str) -> list[str]:
    out: list[str] = []
    for chunk in text.replace("\n", ",").split(","):
        x = chunk.strip().lower()
        if not x:
            continue
        if x not in {t.value for t in RiskTier}:
            raise ValueError(
                "Each approval_required_tiers entry must be one of "
                f"{', '.join(repr(t.value) for t in RiskTier)}"
            )
        out.append(x)
    if not out:
        raise ValueError("Workspace approval tiers must not be empty.")
    return sorted(set(out))


@dataclass(frozen=True)
class WizardTemplate:
    key: str
    title: str
    summary: str
    workspace_description: str
    suggested_display_name: str
    num_total_agents: int
    orch_instructions: str
    worker_instructions: str
    reflection_enabled: bool


WIZARD_TEMPLATES: tuple[WizardTemplate, ...] = (
    WizardTemplate(
        key="blank",
        title="Blank slate",
        summary="Minimal prompts — tune agents after creation.",
        workspace_description="",
        suggested_display_name="MyWorkspace",
        num_total_agents=2,
        orch_instructions="",
        worker_instructions="",
        reflection_enabled=False,
    ),
    WizardTemplate(
        key="quick_demo",
        title="Quick demo (fake models)",
        summary="Two agents with deterministic fake adapters — instant offline smoke tests.",
        workspace_description="Fake-model delegation playground.",
        suggested_display_name="DemoTeam",
        num_total_agents=2,
        orch_instructions="You are the orchestrator. Delegate concrete checks to workers.",
        worker_instructions="Use tools to complete delegated tasks.",
        reflection_enabled=False,
    ),
    WizardTemplate(
        key="code_assistant",
        title="Code & repo workspace",
        summary="Orchestrator + two workers tuned for implementation splits.",
        workspace_description="Multi-agent coding workspace.",
        suggested_display_name="CodeForge",
        num_total_agents=3,
        orch_instructions=(
            "You coordinate repo-wide tasks: divide work, review outputs, "
            "run delegation instead of editing huge blobs yourself."
        ),
        worker_instructions=(
            "You implement concrete edits: read files before writes; "
            "prefer small patches and cite paths."
        ),
        reflection_enabled=False,
    ),
    WizardTemplate(
        key="research",
        title="Research & retrieval",
        summary="Suited for web + memory lookups across specialists.",
        workspace_description="Research-oriented Team Workspace.",
        suggested_display_name="ResearchPods",
        num_total_agents=4,
        orch_instructions=(
            "Assign investigations by specialty; aggregate citations via delegated searches."
        ),
        worker_instructions="Prefer factual summaries with sources when tools provide them.",
        reflection_enabled=False,
    ),
    WizardTemplate(
        key="local_llm",
        title="Local Ollama crew",
        summary="Defaults wired for localhost/Ollama; expand budgets on screen four.",
        workspace_description="On-device agents.",
        suggested_display_name="LocalLab",
        num_total_agents=3,
        orch_instructions="You orchestrate tool-heavy flows entirely against local models.",
        worker_instructions="Be concise and deterministic — hardware latency varies.",
        reflection_enabled=False,
    ),
)


def _instruction_lines(text: str) -> list[str]:
    t = text.strip()
    if not t:
        return []
    collapse = " ".join(t.split())
    escaped = _escape_toml_str(collapse)
    return [f'instructions = "{escaped}"']


def _adapter_blob_lines(wid: str, model_adapter: str, *, fields: dict[str, str]) -> list[str]:
    ma = model_adapter.strip().lower()
    if ma == "fake":
        return []

    if ma == "openai_compat":
        return [
            f"[agents.{wid}.openai_compat]",
            f'model = "{_escape_toml_str(fields["openai_model"].strip())}"',
            f'base_url = "{_escape_toml_str(fields["openai_base_url"].strip())}"',
            f'api_key_env = "{_escape_toml_str(fields["openai_api_key_env"].strip())}"',
            "timeout_seconds = 120.0",
            "",
        ]
    if ma == "anthropic":
        return [
            f"[agents.{wid}.anthropic]",
            f'model = "{_escape_toml_str(fields["anthropic_model"].strip())}"',
            f'api_key_env = "{_escape_toml_str(fields["anthropic_api_key_env"].strip())}"',
            "timeout_seconds = 120.0",
            "",
        ]
    if ma == "gemini":
        return [
            f"[agents.{wid}.gemini]",
            f'model = "{_escape_toml_str(fields["gemini_model"].strip())}"',
            f'api_key_env = "{_escape_toml_str(fields["gemini_api_key_env"].strip())}"',
            "timeout_seconds = 120.0",
            "",
        ]
    if ma == "ollama":
        lines = [
            f"[agents.{wid}.ollama]",
            f'base_url = "{_escape_toml_str(fields["ollama_base_url"].strip())}"',
            f'model = "{_escape_toml_str(fields["ollama_model"].strip())}"',
        ]
        ev = fields.get("ollama_api_key_env", "").strip()
        if ev:
            lines.append(f'api_key_env = "{_escape_toml_str(ev)}"')
        lines.extend(["timeout_seconds = 120.0", ""])
        return lines

    raise ValueError(f"Unknown model_adapter {model_adapter!r}")


def render_workspace_toml(
    *,
    workspace_name: str,
    workspace_description: str,
    trace_dir: str,
    sanitizer_max_chars: int,
    auto_approve: bool,
    approval_required_tiers: str,
    memory_db_path: str,
    num_total_agents: int,
    memory_embeddings: bool,
    reflection_enabled: bool,
    reflection_auto_merge: bool,
    reflection_reliability_gate: bool,
    orch_budget_max_steps: int,
    orch_budget_max_tool_calls: int,
    orch_budget_wall_seconds: float,
    orch_budget_per_tool_seconds: float,
    orch_max_retries: int,
    worker_budget_max_steps: int,
    worker_budget_max_tool_calls: int,
    worker_budget_wall_seconds: float,
    worker_budget_per_tool_seconds: float,
    worker_max_retries: int,
    model_adapter: str = "fake",
    use_full_tool_suite: bool = True,
    orch_instructions: str = "",
    worker_instructions: str = "",
    openai_model: str = "gpt-4o-mini",
    openai_base_url: str = "https://api.openai.com/v1",
    openai_api_key_env: str = "OPENAI_API_KEY",
    anthropic_model: str = "claude-sonnet-4-20250514",
    anthropic_api_key_env: str = "ANTHROPIC_API_KEY",
    gemini_model: str = "gemini-2.0-flash",
    gemini_api_key_env: str = "GEMINI_API_KEY",
    ollama_base_url: str = "http://127.0.0.1:11434",
    ollama_model: str = "llama3.2",
    ollama_api_key_env: str = "",
) -> str:
    """Build ``naqsha.toml`` for a configurable starter team."""

    if num_total_agents < 2:
        raise ValueError("Team needs at least two agents (orchestrator + worker).")
    if num_total_agents > 8:
        raise ValueError("Wizard supports at most eight agents.")
    tiers = _parse_workspace_tiers(approval_required_tiers)

    name = _escape_toml_str(workspace_name.strip() or "team")
    desc = _escape_toml_str(workspace_description)
    traces = _escape_toml_str((trace_dir or ".naqsha/traces").strip())
    tiers_lit = ", ".join(f'"{_escape_toml_str(x)}"' for x in tiers)
    dbp = _escape_toml_str((memory_db_path or ".naqsha/memory.db").strip())
    ma_clean = model_adapter.strip().lower()

    orch = "orch"
    workers = [f"worker{i}" for i in range(1, num_total_agents)]

    power_tools = _sorted_power_tools()

    header_lines: list[str] = [
        "[workspace]",
        f'name = "{name}"',
        f'orchestrator = "{orch}"',
        f'description = "{desc}"',
        f'trace_dir = "{traces}"',
        f"sanitizer_max_chars = {int(sanitizer_max_chars)}",
        "auto_approve = " + str(bool(auto_approve)).lower(),
        f"approval_required_tiers = [{tiers_lit}]",
        "",
        "[memory]",
        'type = "sqlite"',
        f'db_path = "{dbp}"',
        f"embeddings = {str(bool(memory_embeddings)).lower()}",
        "",
        "[reflection]",
        f"enabled = {str(bool(reflection_enabled)).lower()}",
        f"auto_merge = {str(bool(reflection_auto_merge)).lower()}",
        f"reliability_gate = {str(bool(reflection_reliability_gate)).lower()}",
        "",
    ]

    adapter_fields = {
        "openai_model": openai_model,
        "openai_base_url": openai_base_url,
        "openai_api_key_env": openai_api_key_env,
        "anthropic_model": anthropic_model,
        "anthropic_api_key_env": anthropic_api_key_env,
        "gemini_model": gemini_model,
        "gemini_api_key_env": gemini_api_key_env,
        "ollama_base_url": ollama_base_url,
        "ollama_model": ollama_model,
        "ollama_api_key_env": ollama_api_key_env,
    }

    def agent_segment(wid: str) -> list[str]:
        role = "orchestrator" if wid == orch else "worker"
        is_o = wid == orch
        if use_full_tool_suite:
            tools = list(power_tools)
        elif is_o:
            tools = ["clock"]
        else:
            tools = ["clock", "list_memory_tables"]
        tools_lit = ", ".join(f'"{t}"' for t in tools)

        if is_o:
            ms, mc, wt, pt, retries = (
                orch_budget_max_steps,
                orch_budget_max_tool_calls,
                orch_budget_wall_seconds,
                orch_budget_per_tool_seconds,
                orch_max_retries,
            )
            ins_txt = orch_instructions
        else:
            ms, mc, wt, pt, retries = (
                worker_budget_max_steps,
                worker_budget_max_tool_calls,
                worker_budget_wall_seconds,
                worker_budget_per_tool_seconds,
                worker_max_retries,
            )
            ins_txt = worker_instructions

        core_lines = [
            f"[agents.{wid}]",
            f'role = "{role}"',
            f'model_adapter = "{_escape_toml_str(ma_clean)}"',
            f"tools = [{tools_lit}]",
            f"max_retries = {retries}",
            *_instruction_lines(ins_txt),
            "",
            f"[agents.{wid}.budgets]",
            f"max_steps = {ms}",
            f"max_tool_calls = {mc}",
            f"wall_clock_seconds = {float(wt)}",
            f"per_tool_seconds = {float(pt)}",
            "",
        ]
        # Inject adapter tables immediately after budgets block for readability.
        extra = _adapter_blob_lines(wid, ma_clean, fields=adapter_fields)
        if not extra:
            return core_lines
        return core_lines + extra

    segments: list[str] = []
    for wid in [orch, *workers]:
        segments.extend(agent_segment(wid))
    return "\n".join(header_lines + segments) + "\n"


MODEL_ADAPTER_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Fake (offline scripted)", "fake"),
    ("OpenAI-compatible API", "openai_compat"),
    ("Anthropic", "anthropic"),
    ("Google Gemini", "gemini"),
    ("Ollama (local)", "ollama"),
)

_WIZARD_SUBTITLE_FULL = (
    "[dim]Four focused steps · Paste API env names only (never secrets) · "
    "[kbd]ctrl+n[/kbd] next · [kbd]ctrl+b[/kbd] back · "
    "[kbd]ctrl+s[/kbd] save · [kbd]Esc[/kbd] quit[/]"
)
_WIZARD_SUBTITLE_NARROW = (
    "[dim]Steps 1–4 · env var names only · "
    "[kbd]^n[/kbd]/[kbd]^b[/kbd]/[kbd]^s[/kbd] · [kbd]Esc[/kbd] quit[/]"
)


class InitWizardApp(App[None]):
    """Step-through ``naqsha.toml`` wizard with shortcuts matching Command Center style."""

    CSS_PATH = "wizard.tcss"
    BINDINGS = [
        Binding("escape", "quit", "Quit", tooltip="Exit without saving"),
        Binding(
            "ctrl+n",
            "next_step",
            "Next",
            tooltip="Go to the next wizard step",
        ),
        Binding(
            "ctrl+b",
            "prev_step",
            "Back",
            tooltip="Go to the previous wizard step",
        ),
        Binding(
            "ctrl+s",
            "save_workspace",
            "Save",
            tooltip="Write naqsha.toml (also on final step)",
        ),
    ]

    def __init__(self, output_path: Path, *, cwd: Path, profile_name: str) -> None:
        super().__init__()
        self._output_path = output_path.resolve()
        self._cwd = cwd.resolve()
        self._profile_name = profile_name
        self._error: str | None = None
        self._step = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="wizard-shell"):
            yield Static("[bold bright_cyan]NAQSHA · Create a Team Workspace[/]", id="wizard-title")
            yield Static(_WIZARD_SUBTITLE_FULL, id="wizard-sub")

            with ScrollableContainer(id="wizard-steps-scroll"):
                with Vertical(id="wizard-steps-region"):
                    with Vertical(id="step-0", classes="wizard-step"):
                        yield Static("[bold $accent]1 · Template[/]", classes="step-heading")
                        yield Label("Starter blueprint")
                        yield Select(
                            [(t.title, t.key) for t in WIZARD_TEMPLATES],
                            id="template-select",
                            allow_blank=False,
                        )
                        yield Static("", id="template-summary")

                    with Vertical(id="step-1", classes="wizard-step"):
                        yield Static(
                            "[bold $accent]2 · Workspace & provider[/]",
                            classes="step-heading",
                        )
                        yield Label("Display name")
                        yield Input(value="MyWorkspace", id="ws-name", placeholder="e.g. CodeForge")
                        yield Label("Description (optional)")
                        yield Input("", id="ws-desc")
                        with Grid(id="paths-grid"):
                            yield Label("Trace directory")
                            yield Input(value=".naqsha/traces", id="trace-dir")
                            yield Label("Sanitizer max_chars")
                            yield Input(value="65536", id="sanitizer")
                        yield Label("Model backend")
                        yield Select(MODEL_ADAPTER_OPTIONS, id="model-select", allow_blank=False)
                        yield Static(
                            "[bold]API wiring[/] [dim](env var names — never secrets)[/]",
                        )
                        with Vertical(id="provider-openai_compat", classes="provider-sub"):
                            yield Label("[underline]OpenAI-compatible[/]")
                            yield Horizontal(
                                Label("Model", classes="prov-label"),
                                Input(value="gpt-4o-mini", id="openai-model"),
                                classes="prov-row",
                            )
                            yield Horizontal(
                                Label("Base URL", classes="prov-label"),
                                Input(value="https://api.openai.com/v1", id="openai-base-url"),
                                classes="prov-row",
                            )
                            yield Horizontal(
                                Label("API key env", classes="prov-label"),
                                Input(value="OPENAI_API_KEY", id="openai-env"),
                                classes="prov-row",
                            )
                        with Vertical(id="provider-anthropic", classes="provider-sub"):
                            yield Label("[underline]Anthropic[/]")
                            yield Horizontal(
                                Label("Model", classes="prov-label"),
                                Input(value="claude-sonnet-4-20250514", id="anthropic-model"),
                                classes="prov-row",
                            )
                            yield Horizontal(
                                Label("API key env", classes="prov-label"),
                                Input(value="ANTHROPIC_API_KEY", id="anthropic-env"),
                                classes="prov-row",
                            )
                        with Vertical(id="provider-gemini", classes="provider-sub"):
                            yield Label("[underline]Gemini[/]")
                            yield Horizontal(
                                Label("Model", classes="prov-label"),
                                Input(value="gemini-2.0-flash", id="gemini-model"),
                                classes="prov-row",
                            )
                            yield Horizontal(
                                Label("API key env", classes="prov-label"),
                                Input(value="GEMINI_API_KEY", id="gemini-env"),
                                classes="prov-row",
                            )
                        with Vertical(id="provider-ollama", classes="provider-sub"):
                            yield Label("[underline]Ollama[/]")
                            yield Horizontal(
                                Label("Host URL", classes="prov-label"),
                                Input(value="http://127.0.0.1:11434", id="ollama-url"),
                                classes="prov-row",
                            )
                            yield Horizontal(
                                Label("Model", classes="prov-label"),
                                Input(value="llama3.2", id="ollama-model"),
                                classes="prov-row",
                            )
                            yield Horizontal(
                                Label("Bearer env [dim](optional)[/]", classes="prov-label"),
                                Input("", id="ollama-env", placeholder="usually blank"),
                                classes="prov-row",
                            )

                    with Vertical(id="step-2", classes="wizard-step"):
                        yield Static(
                            "[bold $accent]3 · Team & policy[/]",
                            classes="step-heading",
                        )
                        yield Checkbox(
                            (
                                "[bold yellow]workspace.auto_approve[/] — skip stdin "
                                "approvals locally (recommended)"
                            ),
                            id="auto-ap",
                            value=True,
                        )
                        yield Label(
                            "Approval tiers tracked [dim](write/high tier labels persist)[/]"
                        )
                        yield Input(value="write,high", id="tiers-txt")
                        with Grid(id="team-grid"):
                            yield Label("Agents total [dim](orchestrator + workers)[/]")
                            yield Input(value="2", id="agent-count")
                            yield Label("SQLite DB path")
                            yield Input(value=".naqsha/memory.db", id="mem-db")
                        yield Checkbox(
                            "sqlite-vec embeddings [dim](requires extras)[/]",
                            id="mem-emb",
                            value=False,
                        )
                        yield Label("[bold]Reflection[/]")
                        yield Checkbox("Enable Reflection Loop", id="refl-on", value=False)
                        yield Checkbox(
                            "Allow auto-merge after gate "
                            "[dim](still gated — reliability enforced)[/]",
                            id="refl-merge",
                            value=False,
                        )
                        yield Checkbox(
                            "Require pytest Reliability Gate before merge",
                            id="refl-gate",
                            value=True,
                        )

                        yield Static(
                            "[bold]Per-role prompts[/] "
                            "[dim](single-line; refined later in Config)[/]"
                        )
                        yield Label("Orchestrator instructions")
                        yield Input("", id="orch-inst")
                        yield Label("Worker instructions")
                        yield Input("", id="worker-inst")

                    with Vertical(id="step-3", classes="wizard-step"):
                        yield Static(
                            "[bold $accent]4 · Budgets & create[/]",
                            classes="step-heading",
                        )
                        yield Checkbox(
                            "Use recommended generous budgets [dim](or tune manually)[/]",
                            id="use-power-budgets",
                            value=True,
                        )
                        yield Static("[bold]Orchestrator budgets[/]", classes="budget-mini-head")
                        with Grid(id="orch-b-grid"):
                            yield Label("max_steps")
                            yield Input(value=str(POWER_ORCH_BUDGET.max_steps), id="orch-ms")
                            yield Label("max_tool_calls")
                            yield Input(value=str(POWER_ORCH_BUDGET.max_tool_calls), id="orch-mtc")
                            yield Label("wall_clock_seconds")
                            yield Input(
                                value=str(POWER_ORCH_BUDGET.wall_clock_seconds),
                                id="orch-wall",
                            )
                            yield Label("per_tool_seconds")
                            yield Input(value=str(POWER_ORCH_BUDGET.per_tool_seconds), id="orch-pt")
                            yield Label("max_retries")
                            yield Input(value="5", id="orch-retry")
                        yield Static("[bold]Worker budgets[/]", classes="budget-mini-head")
                        with Grid(id="wk-b-grid"):
                            yield Label("max_steps")
                            yield Input(value=str(POWER_WORKER_BUDGET.max_steps), id="wk-ms")
                            yield Label("max_tool_calls")
                            yield Input(value=str(POWER_WORKER_BUDGET.max_tool_calls), id="wk-mtc")
                            yield Label("wall_clock_seconds")
                            yield Input(
                                value=str(POWER_WORKER_BUDGET.wall_clock_seconds),
                                id="wk-wall",
                            )
                            yield Label("per_tool_seconds")
                            yield Input(value=str(POWER_WORKER_BUDGET.per_tool_seconds), id="wk-pt")
                            yield Label("max_retries")
                            yield Input(value="5", id="wk-retry")

                        yield Checkbox(
                            "Expose entire Starter Tool Set + memory DDL helpers",
                            id="full-tools",
                            value=True,
                        )

            with Horizontal(id="wizard-nav-bar"):
                yield Button("Back", id="btn-prev", variant="default")
                yield Button("Next", id="btn-next", variant="primary")
                yield Button("Save workspace", id="save", variant="success")

            yield Static("", id="wizard-status")

            yield Static(
                "[dim]#4 Finish saves · Starter presets hydrate screens "
                "2–3; adjust provider/env vars before Save[/]",
                id="wizard-footer-hint",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.title = "NAQSHA init"
        self.theme = "tokyo-night"
        self.sub_title = "^N Next · ^B Back · ^S Save · Esc Quit"
        tpl_sel = self.query_one("#template-select", Select)
        tpl_sel.value = WIZARD_TEMPLATES[0].key
        self._apply_template(WIZARD_TEMPLATES[0])
        self._sync_provider_panel_visibility()
        self._refresh_step_visibility()

        if os.environ.get("NAQSHA_TEST_WIZARD_AUTOSAVE") == "1":
            if self._write_from_fields_expect_success(autosave_test_defaults=True):
                self.exit(0)

    def on_resize(self, event: events.Resize) -> None:
        """Swap subtitle density so hints stay readable on narrow terminals."""
        sub = self.query_one("#wizard-sub", Static)
        if event.size.width < 76:
            sub.update(_WIZARD_SUBTITLE_NARROW)
        else:
            sub.update(_WIZARD_SUBTITLE_FULL)

    def _wizard_templates_by_key(self) -> dict[str, WizardTemplate]:
        return {t.key: t for t in WIZARD_TEMPLATES}

    def _current_adapter_value(self) -> str:
        sel = self.query_one("#model-select", Select)
        raw = sel.value
        return str(raw) if raw is not None else "fake"

    def _refresh_step_visibility(self) -> None:
        hint = self.query_one("#wizard-footer-hint", Static)
        hints = (
            "#1 Pick a preset blueprint · Fields below hydrate workspace basics.",
            "#2 Name the workspace · Pick backend · Paste env-var names your shell exports.",
            "#3 Policy defaults favour frictionless local runs · Reflection stays opt-in.",
            "#4 Budgets sized for serious sessions · Save writes naqsha.toml.",
        )
        hint.update(f"[dim]{hints[self._step]}[/]")
        for i in range(4):
            panel = self.query_one(f"#step-{i}", Vertical)
            panel.set_class(i != self._step, "step-hidden")

        prev_b = self.query_one("#btn-prev", Button)
        next_b = self.query_one("#btn-next", Button)
        prev_b.disabled = self._step == 0
        next_b.disabled = self._step >= 3

    def action_prev_step(self) -> None:
        self._step = max(0, self._step - 1)
        self._refresh_step_visibility()

    def action_next_step(self) -> None:
        self._step = min(3, self._step + 1)
        self._refresh_step_visibility()

    def action_save_workspace(self) -> None:
        self._gather_save()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-prev":
            self.action_prev_step()
        elif event.button.id == "btn-next":
            self.action_next_step()
        elif event.button.id == "save":
            self._gather_save()

    @on(Select.Changed, "#template-select")
    def template_changed(self, event: Select.Changed) -> None:
        raw = event.value
        key = str(raw) if raw is not None else WIZARD_TEMPLATES[0].key
        tpl = self._wizard_templates_by_key().get(key)
        if tpl is None:
            return
        self._apply_template(tpl)

    @on(Select.Changed, "#model-select")
    def model_changed(self, _event: Select.Changed) -> None:
        self._sync_provider_panel_visibility()

    def _apply_template(self, tpl: WizardTemplate) -> None:
        summary = self.query_one("#template-summary", Static)
        summary.update(f"[#89ddff]{tpl.summary}[/]")
        name_in = self.query_one("#ws-name", Input)
        desc_in = self.query_one("#ws-desc", Input)
        name_in.value = tpl.suggested_display_name
        desc_in.value = tpl.workspace_description
        ac = self.query_one("#agent-count", Input)
        ac.value = str(tpl.num_total_agents)
        orch_i = self.query_one("#orch-inst", Input)
        worker_i = self.query_one("#worker-inst", Input)
        orch_i.value = tpl.orch_instructions
        worker_i.value = tpl.worker_instructions
        refl = self.query_one("#refl-on", Checkbox)
        refl.value = tpl.reflection_enabled

        if tpl.key == "local_llm":
            sel = self.query_one("#model-select", Select)
            sel.value = "ollama"

        self._sync_provider_panel_visibility()

    def _sync_provider_panel_visibility(self) -> None:
        adapter = self._current_adapter_value()
        for aid, node_id in (
            ("openai_compat", "provider-openai_compat"),
            ("anthropic", "provider-anthropic"),
            ("gemini", "provider-gemini"),
            ("ollama", "provider-ollama"),
        ):
            block = self.query_one(f"#{node_id}", Vertical)
            block.set_class(not (adapter == aid), "provider-hidden")

    def action_quit(self) -> None:
        self.exit()

    def _set_error(self, msg: str) -> None:
        self._error = msg
        self.query_one("#wizard-status", Static).update(f"[red]{msg}[/]")

    @staticmethod
    def _positive_int(raw: str, _lbl: str) -> int | None:
        try:
            v = int(raw.strip())
            if v < 1:
                raise ValueError
            return v
        except ValueError:
            return None

    @staticmethod
    def _positive_float(raw: str, _lbl: str) -> float | None:
        try:
            v = float(raw.strip())
            if v <= 0:
                raise ValueError
            return v
        except ValueError:
            return None

    @staticmethod
    def _nonneg_int(raw: str) -> int | None:
        try:
            v = int(raw.strip())
            if v < 0:
                raise ValueError
            return v
        except ValueError:
            return None

    def _gather_save(self) -> None:
        if self._write_from_fields_expect_success(autosave_test_defaults=False):
            self.exit(0)

    def _apply_power_budget_checkbox(self) -> None:
        use_pb = self.query_one("#use-power-budgets", Checkbox).value
        orch_pairs = (
            ("#orch-ms", str(POWER_ORCH_BUDGET.max_steps)),
            ("#orch-mtc", str(POWER_ORCH_BUDGET.max_tool_calls)),
            ("#orch-wall", str(POWER_ORCH_BUDGET.wall_clock_seconds)),
            ("#orch-pt", str(POWER_ORCH_BUDGET.per_tool_seconds)),
        )
        wk_pairs = (
            ("#wk-ms", str(POWER_WORKER_BUDGET.max_steps)),
            ("#wk-mtc", str(POWER_WORKER_BUDGET.max_tool_calls)),
            ("#wk-wall", str(POWER_WORKER_BUDGET.wall_clock_seconds)),
            ("#wk-pt", str(POWER_WORKER_BUDGET.per_tool_seconds)),
        )
        if use_pb:
            for cid, val in orch_pairs + wk_pairs:
                self.query_one(cid, Input).value = val

    def _write_from_fields_expect_success(
        self, *, autosave_test_defaults: bool
    ) -> bool:
        if autosave_test_defaults:
            ws = "TestTeam"
            desc = ""
            traces = ".naqsha/traces"
            sane = 4000
            auto_ap = False
            tiers_txt = "write,high"
            num = 2
            mem_emb = False
            refl_on = False
            refl_merge = False
            refl_gate = True
            mem_db = ".naqsha/memory.db"
            ma = "fake"
            full_suite = False
            orch_inst = ""
            worker_inst = ""
            orch_ms = _DEF_BUDGET.max_steps
            orch_mtc = _DEF_BUDGET.max_tool_calls
            orch_wall = _DEF_BUDGET.wall_clock_seconds
            orch_pt = _DEF_BUDGET.per_tool_seconds
            orch_rt = 3
            wk_ms = _DEF_BUDGET.max_steps
            wk_mtc = _DEF_BUDGET.max_tool_calls
            wk_wall = _DEF_BUDGET.wall_clock_seconds
            wk_pt = _DEF_BUDGET.per_tool_seconds
            wk_rt = 3
            openai_model_v = "gpt-4o-mini"
            openai_base_v = "https://api.openai.com/v1"
            openai_env_v = "OPENAI_API_KEY"
            anthropic_model_v = "claude-sonnet-4-20250514"
            anthropic_env_v = "ANTHROPIC_API_KEY"
            gemini_model_v = "gemini-2.0-flash"
            gemini_env_v = "GEMINI_API_KEY"
            ollama_url_v = "http://127.0.0.1:11434"
            ollama_model_v = "llama3.2"
            ollama_env_v = ""
        else:
            self._apply_power_budget_checkbox()
            ws = self.query_one("#ws-name", Input).value.strip() or "MyWorkspace"
            desc = self.query_one("#ws-desc", Input).value
            traces = self.query_one("#trace-dir", Input).value.strip() or ".naqsha/traces"
            raw_sane = self.query_one("#sanitizer", Input).value.strip() or "65536"
            try:
                sane = max(1024, int(raw_sane))
            except ValueError:
                self._set_error("Sanitizer limit must be a positive integer.")
                return False
            auto_ap = self.query_one("#auto-ap", Checkbox).value
            tiers_txt = self.query_one("#tiers-txt", Input).value or "write,high"
            raw_n = self.query_one("#agent-count", Input).value.strip() or "2"
            try:
                num = int(raw_n)
            except ValueError:
                self._set_error("Agent count must be an integer.")
                return False
            mem_emb = self.query_one("#mem-emb", Checkbox).value
            refl_on = self.query_one("#refl-on", Checkbox).value
            refl_merge = self.query_one("#refl-merge", Checkbox).value
            refl_gate = self.query_one("#refl-gate", Checkbox).value
            mem_db = self.query_one("#mem-db", Input).value.strip() or ".naqsha/memory.db"
            ma_raw = self._current_adapter_value()
            ma = str(ma_raw).strip().lower()
            full_suite = self.query_one("#full-tools", Checkbox).value
            orch_inst = self.query_one("#orch-inst", Input).value
            worker_inst = self.query_one("#worker-inst", Input).value

            openai_model_v = self.query_one("#openai-model", Input).value.strip() or "gpt-4o-mini"
            openai_base_v = (
                self.query_one("#openai-base-url", Input).value.strip()
                or "https://api.openai.com/v1"
            )
            openai_env_v = (
                self.query_one("#openai-env", Input).value.strip() or "OPENAI_API_KEY"
            )
            anthropic_model_v = (
                self.query_one("#anthropic-model", Input).value.strip()
                or "claude-sonnet-4-20250514"
            )
            anthropic_env_v = (
                self.query_one("#anthropic-env", Input).value.strip() or "ANTHROPIC_API_KEY"
            )
            gemini_model_v = (
                self.query_one("#gemini-model", Input).value.strip() or "gemini-2.0-flash"
            )
            gemini_env_v = (
                self.query_one("#gemini-env", Input).value.strip() or "GEMINI_API_KEY"
            )
            ollama_url_v = (
                self.query_one("#ollama-url", Input).value.strip()
                or "http://127.0.0.1:11434"
            )
            ollama_model_v = self.query_one("#ollama-model", Input).value.strip() or "llama3.2"
            ollama_env_v = self.query_one("#ollama-env", Input).value.strip()

            if refl_merge and not refl_on:
                self._set_error("Auto-merge requires Reflection Loop to be enabled.")
                return False

            orch_ms = self._positive_int(self.query_one("#orch-ms", Input).value, "")
            orch_mtc = self._positive_int(self.query_one("#orch-mtc", Input).value, "")
            orch_wall = self._positive_float(self.query_one("#orch-wall", Input).value, "")
            orch_pt = self._positive_float(self.query_one("#orch-pt", Input).value, "")
            orch_rt = self._nonneg_int(self.query_one("#orch-retry", Input).value)

            wk_ms = self._positive_int(self.query_one("#wk-ms", Input).value, "")
            wk_mtc = self._positive_int(self.query_one("#wk-mtc", Input).value, "")
            wk_wall = self._positive_float(self.query_one("#wk-wall", Input).value, "")
            wk_pt = self._positive_float(self.query_one("#wk-pt", Input).value, "")
            wk_rt = self._nonneg_int(self.query_one("#wk-retry", Input).value)

            for tup, lbl in (
                (orch_ms, "orch max_steps"),
                (orch_mtc, "orch max_tool_calls"),
                (wk_ms, "worker max_steps"),
                (wk_mtc, "worker max_tool_calls"),
            ):
                if tup is None:
                    self._set_error(f"{lbl} must be a positive integer.")
                    return False
            if orch_wall is None or orch_pt is None or wk_wall is None or wk_pt is None:
                self._set_error("Wall / per_tool seconds must be positive numbers.")
                return False
            if orch_rt is None or wk_rt is None:
                self._set_error("max_retries must be a non‑negative integer.")
                return False

        return self._write_toml(
            workspace_name=ws,
            workspace_description=desc,
            trace_dir=traces,
            sanitizer_max_chars=sane,
            auto_approve=auto_ap,
            approval_required_tiers=tiers_txt,
            memory_db_path=mem_db,
            num_agents=num,
            memory_embeddings=mem_emb,
            reflection_enabled=refl_on,
            reflection_auto_merge=refl_merge,
            reflection_reliability_gate=refl_gate,
            orch_budget_max_steps=int(orch_ms),
            orch_budget_max_tool_calls=int(orch_mtc),
            orch_budget_wall_seconds=float(orch_wall),
            orch_budget_per_tool_seconds=float(orch_pt),
            orch_max_retries=int(orch_rt),
            worker_budget_max_steps=int(wk_ms),
            worker_budget_max_tool_calls=int(wk_mtc),
            worker_budget_wall_seconds=float(wk_wall),
            worker_budget_per_tool_seconds=float(wk_pt),
            worker_max_retries=int(wk_rt),
            model_adapter=ma,
            use_full_tool_suite=full_suite,
            orch_instructions=orch_inst,
            worker_instructions=worker_inst,
            openai_model=openai_model_v,
            openai_base_url=openai_base_v,
            openai_api_key_env=openai_env_v,
            anthropic_model=anthropic_model_v,
            anthropic_api_key_env=anthropic_env_v,
            gemini_model=gemini_model_v,
            gemini_api_key_env=gemini_env_v,
            ollama_base_url=ollama_url_v,
            ollama_model=ollama_model_v,
            ollama_api_key_env=ollama_env_v,
        )

    def _write_toml(
        self,
        *,
        workspace_name: str,
        workspace_description: str,
        trace_dir: str,
        sanitizer_max_chars: int,
        auto_approve: bool,
        approval_required_tiers: str,
        memory_db_path: str,
        num_agents: int,
        memory_embeddings: bool,
        reflection_enabled: bool,
        reflection_auto_merge: bool,
        reflection_reliability_gate: bool,
        orch_budget_max_steps: int,
        orch_budget_max_tool_calls: int,
        orch_budget_wall_seconds: float,
        orch_budget_per_tool_seconds: float,
        orch_max_retries: int,
        worker_budget_max_steps: int,
        worker_budget_max_tool_calls: int,
        worker_budget_wall_seconds: float,
        worker_budget_per_tool_seconds: float,
        worker_max_retries: int,
        model_adapter: str,
        use_full_tool_suite: bool,
        orch_instructions: str,
        worker_instructions: str,
        openai_model: str,
        openai_base_url: str,
        openai_api_key_env: str,
        anthropic_model: str,
        anthropic_api_key_env: str,
        gemini_model: str,
        gemini_api_key_env: str,
        ollama_base_url: str,
        ollama_model: str,
        ollama_api_key_env: str,
    ) -> bool:
        try:
            body = render_workspace_toml(
                workspace_name=workspace_name,
                workspace_description=workspace_description,
                trace_dir=trace_dir,
                sanitizer_max_chars=sanitizer_max_chars,
                auto_approve=auto_approve,
                approval_required_tiers=approval_required_tiers,
                memory_db_path=memory_db_path,
                num_total_agents=num_agents,
                memory_embeddings=memory_embeddings,
                reflection_enabled=reflection_enabled,
                reflection_auto_merge=reflection_auto_merge,
                reflection_reliability_gate=reflection_reliability_gate,
                orch_budget_max_steps=orch_budget_max_steps,
                orch_budget_max_tool_calls=orch_budget_max_tool_calls,
                orch_budget_wall_seconds=orch_budget_wall_seconds,
                orch_budget_per_tool_seconds=orch_budget_per_tool_seconds,
                orch_max_retries=orch_max_retries,
                worker_budget_max_steps=worker_budget_max_steps,
                worker_budget_max_tool_calls=worker_budget_max_tool_calls,
                worker_budget_wall_seconds=worker_budget_wall_seconds,
                worker_budget_per_tool_seconds=worker_budget_per_tool_seconds,
                worker_max_retries=worker_max_retries,
                model_adapter=model_adapter,
                use_full_tool_suite=use_full_tool_suite,
                orch_instructions=orch_instructions,
                worker_instructions=worker_instructions,
                openai_model=openai_model,
                openai_base_url=openai_base_url,
                openai_api_key_env=openai_api_key_env,
                anthropic_model=anthropic_model,
                anthropic_api_key_env=anthropic_api_key_env,
                gemini_model=gemini_model,
                gemini_api_key_env=gemini_api_key_env,
                ollama_base_url=ollama_base_url,
                ollama_model=ollama_model,
                ollama_api_key_env=ollama_api_key_env,
            )
            parse_team_topology(tomllib.loads(body), base_dir=self._cwd)
        except Exception as exc:
            self._set_error(str(exc))
            return False
        init_agent_project(self._cwd, profile_name=self._profile_name)
        self._output_path.write_text(body, encoding="utf-8")
        self.query_one("#wizard-status", Static).update(f"[green]Wrote {self._output_path}[/]")
        return True


def run_init_wizard(*, cwd: Path, profile_name: str) -> Path:
    """Create ``.naqsha/`` layout and ``naqsha.toml`` via the Textual wizard."""

    out = (cwd / "naqsha.toml").resolve()
    InitWizardApp(out, cwd=cwd, profile_name=profile_name).run()
    return out

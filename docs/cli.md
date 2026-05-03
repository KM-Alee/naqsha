# CLI and Workbench TUI

The `naqsha` console script is defined in `pyproject.toml` and dispatches subcommands from `naqsha.cli`.

```
naqsha [--profile PROFILE] <command> [options]
```

The default `--profile` is `local-fake` (bundled; no API keys). After `naqsha init`, use `workbench`.

---

## `naqsha init`

Initialise a **Team Workspace** in the current directory.

```bash
naqsha init [--no-tui]
```

Creates `.naqsha/` directories and a starter `naqsha.toml`.

When `textual` is installed (`[tui]` extra) and stdin/stdout are TTYs, the **init wizard** (`InitWizardApp`) opens interactively — ask for workspace name, model provider, and tool preferences, then writes a valid `naqsha.toml`.

Set `NAQSHA_NO_TUI=1` or pass `--no-tui` to skip the wizard and write a default config.

---

## `naqsha run`

Execute a single-agent run from a **Run Profile**.

```bash
naqsha run [--profile PROFILE] [--human] [--approve-prompt] [--no-tui] "QUERY"
```

| Option | Description |
|---|---|
| `--profile` | Run Profile name or path (default: `local-fake`) |
| `--human` | Print the agent's answer to stdout instead of structured JSON |
| `--approve-prompt` | Enable interactive Approval Gate prompts for `write`-tier tools |
| `--no-tui` | Force plain output; same as `NAQSHA_NO_TUI=1` |

When the `[tui]` extra is installed and stdin/stdout are TTYs, `naqsha run` opens **`WorkbenchApp`** with live Chat, Budget, Span Tree, Flame, Memory Browser, and Patch Review panels all wired to the `RuntimeEventBus`.

Structured JSON output (default, no `--human`) includes:

```json
{
  "run_id": "abc123",
  "answer": "...",
  "failed": false,
  "steps": 3,
  "tokens_used": 512
}
```

---

## `naqsha replay`

Inspect or re-execute a completed trace.

```bash
naqsha replay [--profile PROFILE] [--latest | RUN_ID] [--human] [--re-execute]
```

| Option | Description |
|---|---|
| `--latest` | Use the most recent trace |
| `RUN_ID` | Specific run to replay |
| `--human` | Print trace summary in human-readable form |
| `--re-execute` | Re-run against recorded observations (deterministic; no network calls) |

`--re-execute` uses `TraceReplayModelClient`: the model client returns recorded NAP messages in order; tool observations are served from the trace's `call_id`-indexed observation map. This makes regression testing deterministic even without API keys.

---

## `naqsha trace inspect`

Summarise a trace without re-executing.

```bash
naqsha trace inspect [--profile PROFILE] [--latest | RUN_ID]
```

---

## `naqsha profile show`

Print the resolved **Run Profile** as JSON.

```bash
naqsha profile show [--profile PROFILE]
```

---

## `naqsha profile inspect-policy`

Print the effective **Tool Policy** for a Run Profile.

```bash
naqsha profile inspect-policy [--profile PROFILE]
```

Useful before enabling approvals — verify which tools require human sign-off.

---

## `naqsha tools list`

List all tools that the resolved Run Profile permits, with risk tiers.

```bash
naqsha tools list [--profile PROFILE]
```

---

## `naqsha eval save`

Snapshot a completed run as a **regression fixture**.

```bash
naqsha eval save [--profile PROFILE] RUN_ID FIXTURE_NAME
```

Writes a schema-versioned JSON fixture to `.naqsha/evals/<FIXTURE_NAME>.json`.

---

## `naqsha eval check`

Verify a completed run against a saved fixture.

```bash
naqsha eval check [--profile PROFILE] RUN_ID --name FIXTURE_NAME
```

Exits non-zero if the run output differs from the fixture.

---

## `naqsha reflect` / `naqsha improve`

Generate a **Reflection Patch** workspace from a completed run.

```bash
naqsha reflect [--profile PROFILE] RUN_ID [--workspace-base DIR]
naqsha improve [--profile PROFILE] RUN_ID [--workspace-base DIR]
```

Both commands are aliases. The patch workspace is created under `--workspace-base` (default: `.naqsha/reflection-workspaces/`).

JSON output includes `auto_merged: true/false` so CI can distinguish human-review patches from auto-merged ones.

---

## Workbench TUI

The **Workbench TUI** is a Textual-based terminal UI powered by the **Typed Event Bus**. It opens automatically during `naqsha run` and `naqsha init` when:

1. The `[tui]` extra is installed (`pip install "naqsha[tui]"`).
2. Both stdin and stdout are TTYs.
3. `NAQSHA_NO_TUI` is not set to `1`.

### Panels

| Panel | Bus events consumed | Description |
|---|---|---|
| **Chat** | `StreamChunkReceived`, `ToolInvoked`, `ToolCompleted`, `ToolErrored`, `RunCompleted`, `RunFailed` | Streaming token output and tool call log |
| **Budget** | `BudgetProgress` | Live step / tool-call / wall-clock progress bars |
| **Span Tree** | `SpanOpened`, `SpanClosed` | Expandable trace tree with span hierarchy |
| **Flame Graph** | `SpanOpened`, `SpanClosed` | Per-agent wall time and token totals |
| **Memory Browser** | *(no bus; reads DB directly)* | Read-only SQLite table viewer for `.naqsha/memory.db` |
| **Patch Review** | `PatchMerged`, `PatchRolledBack` | Diff preview with Approve / Reject buttons |

### Patch review

The **Patch Review Panel** lists `reflection-patch-*` workspaces under `.naqsha/reflection-workspaces/`, shows side-by-side text diffs, and routes:

- **Approve** → `approve_patch(patch_id)` → `PatchMerged` event on the bus
- **Reject** → `reject_patch(patch_id)` → workspace removed

### Theme

The Workbench TUI uses the **`tokyo-night`** theme by default. Colour scheme, typography, and spacing are defined in `tui/workbench.tcss`.

---

## Environment variables

| Variable | Description |
|---|---|
| `NAQSHA_NO_TUI` | Set to `1` to force plain JSON/text output; prevents TUI from opening |
| `OPENAI_API_KEY` | Referenced by `api_key_env = "OPENAI_API_KEY"` in profiles |
| `ANTHROPIC_API_KEY` | Referenced by `api_key_env = "ANTHROPIC_API_KEY"` |
| `GOOGLE_API_KEY` | Referenced by `api_key_env = "GOOGLE_API_KEY"` |

---

## Library embedding

For programmatic use, bypass the CLI and use `naqsha.wiring` directly:

```python
from naqsha.wiring import build_runtime, build_trace_replay_runtime
from naqsha.profiles import load_run_profile
from naqsha import RuntimeEventBus

bus = RuntimeEventBus()
runtime = build_runtime(load_run_profile("local-fake"), event_bus=bus)
result = runtime.run("ping")
```

For multi-agent teams:

```python
from naqsha.orchestration.team_runtime import build_team_orchestrator_runtime
from naqsha.orchestration.topology import parse_team_topology_file

rt = build_team_orchestrator_runtime(
    parse_team_topology_file(Path("naqsha.toml")),
    workspace_path=Path("."),
    event_bus=bus,
)
result = rt.run("start")
```

---

## Further reading

- API: [`naqsha.tui`](reference/tui.md)
- API: [`naqsha` (public)](reference/naqsha.md)
- ADR: [0008 — Rich TUI for Agent Workbench](https://github.com/KM-Alee/naqsha/blob/main/docs/adr/0008-rich-tui-for-agent-workbench.md)

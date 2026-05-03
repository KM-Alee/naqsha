# Getting started

This guide walks you from a clean Python environment to a running NAQSHA agent — with no API keys required for the initial examples.

---

## Requirements

- Python 3.11 or 3.12
- [`uv`](https://docs.astral.sh/uv/) (recommended) **or** `pip`

---

## Install

=== "pip"

    ```bash
    pip install naqsha
    ```

=== "pip (with TUI)"

    ```bash
    pip install "naqsha[tui]"
    ```

=== "uv (from a clone)"

    ```bash
    git clone https://github.com/KM-Alee/naqsha.git
    cd naqsha
    uv sync --extra dev
    ```

Confirm the install:

```bash
naqsha --version
# → naqsha 0.2.0
```

---

## Offline run (no API keys)

The bundled **`local-fake`** Run Profile uses a scripted model client. It exercises the full Core Runtime — tool dispatch, trace writing, budget tracking — without making any network calls:

```bash
naqsha run --profile local-fake --human "ping"
# → pong
```

The `--human` flag prints the agent's answer to stdout. Without it you get structured JSON.

---

## Initialise a workspace

For a real workspace with traces and profiles stored under `.naqsha/`:

```bash
mkdir my-project && cd my-project
naqsha init
```

If `textual` is installed (the `[tui]` extra) and you are in an interactive terminal, the **init wizard** opens automatically. It asks for your project name, model provider, and tool preferences, then writes a valid `naqsha.toml`.

Set `NAQSHA_NO_TUI=1` to skip the wizard and write a default config instead.

After init:

```bash
naqsha run --profile workbench --human "hello"
```

---

## Single-agent run with a real model

Add a `profiles/openai.json` (or edit `naqsha.toml` under `[agents.orch]`) with your provider's settings:

```json
{
  "profile": "openai",
  "model_adapter": "openai_compat",
  "model": "gpt-4o",
  "api_base": "https://api.openai.com/v1",
  "api_key_env": "OPENAI_API_KEY",
  "tools": ["clock", "read_file", "list_files"],
  "trace_dir": ".naqsha/traces",
  "max_steps": 10
}
```

!!! warning "Credentials"
    `api_key_env` stores the **environment variable name**, never the key value itself. The actual key lives in your shell environment or `.env` file — never in a committed config file.

```bash
export OPENAI_API_KEY="sk-..."
naqsha run --profile openai --human "What files are in this directory?"
```

---

## Inspect a trace

Every run writes an append-only JSONL trace under `.naqsha/traces/`.

```bash
# Human-readable summary of the latest trace
naqsha replay --profile workbench --latest --human

# Re-execute against recorded observations (deterministic; no network calls)
naqsha replay --profile workbench --latest --re-execute
```

---

## Regression fixtures

Snapshot a run to catch regressions:

```bash
# Get the run_id from the JSON stdout or the stderr hint printed after a run
naqsha eval save --profile workbench <run_id> smoke

# Later: re-run and verify outputs match
naqsha eval check --profile workbench <run_id> --name smoke
```

Fixtures are stored under `.naqsha/evals/` as schema-versioned JSON files.

---

## Team Workspace (two-agent fake model, no keys)

Multi-agent teams are defined in `naqsha.toml`. Here is a minimal fake-model team:

```bash
mkdir demo-team && cd demo-team
mkdir -p .naqsha/traces
```

Create `naqsha.toml`:

```toml
[workspace]
name         = "demo"
orchestrator = "orch"
auto_approve = true

[memory]
db_path = ".naqsha/memory.db"

[reflection]

[agents.orch]
role          = "orchestrator"
model_adapter = "fake"
tools         = ["clock"]

[agents.orch.fake_model]
messages = [
  { kind = "action", calls = [
    { id = "d1", name = "delegate_to_worker", arguments = { task = "hello" } },
  ]},
  { kind = "answer", text = "orch done" },
]

[agents.worker]
role          = "worker"
model_adapter = "fake"
tools         = ["clock", "list_memory_tables"]

[agents.worker.fake_model]
messages = [
  { kind = "action", calls = [
    { id = "c1", name = "clock", arguments = {} },
  ]},
  { kind = "answer", text = "worker was here" },
]
```

Run the team via the Python API:

```python
from pathlib import Path
from naqsha.orchestration.team_runtime import build_team_orchestrator_runtime
from naqsha.orchestration.topology import parse_team_topology_file

root = Path(".")
topo = parse_team_topology_file(root / "naqsha.toml")
rt   = build_team_orchestrator_runtime(topo, root)
res  = rt.run("start")
print("failed:", res.failed, "answer:", res.answer)
# → failed: False  answer: orch done
```

Expected output: a hierarchical trace under `.naqsha/traces/` with both `orch` and `worker` `agent_id` values.

---

## Interactive Workbench TUI

Install the `[tui]` extra:

```bash
pip install "naqsha[tui]"
```

The TUI opens automatically when stdin/stdout are TTYs:

```bash
naqsha run --profile workbench "Analyse recent traces"
```

To force plain output: `NAQSHA_NO_TUI=1 naqsha run ...`

---

## Next steps

- **[Concepts and vocabulary →](concepts.md)** — understand the NAQSHA mental model
- **[Decorator-Driven API →](tools.md)** — define your own tools with `@agent.tool`
- **[Multi-agent teams →](teams.md)** — build an orchestrator + worker topology
- **[Dynamic Memory →](memory.md)** — share knowledge across agents
- **[Reflection and rollback →](reflection.md)** — autonomous improvement with safety gates
- **[CLI reference →](cli.md)** — full command reference
- **[API reference →](reference/index.md)** — auto-generated from docstrings

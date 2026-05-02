# NAQSHA

NAQSHA is a minimal Python **agent runtime** (**Core Runtime**) with strict **NAP Actions**, append-only **QAOA Traces**, enforced **Tool Policy**, **Approval Gates**, durable **Memory Port** adapters, and trace **replay**.

The PyPI distribution, import package, and CLI command are `naqsha`.

## Agent Workbench

For day-to-day use, think in terms of the **Agent Workbench**: initialize a `.naqsha/` agent project, run queries, inspect traces, replay and **eval** regressions, and optionally open **Reflection Patches** for **reviewed self-improvement** (nothing auto-merges into the runtime). See ADR `docs/adr/0005-agent-workbench-and-reviewed-self-improvement.md`.

### Flagship walkthrough

After `pip install naqsha` (or editable install):

```bash
mkdir demo && cd demo
naqsha init
naqsha run --profile workbench "ping"
# Copy run_id from the JSON line stdout (or omit --human to get stderr replay hint).
naqsha replay --profile workbench <run_id> --human
naqsha eval save --profile workbench <run_id> smoke
naqsha eval check --profile workbench <run_id> --name smoke
naqsha reflect --profile workbench <run_id>
# equivalent: naqsha improve ...
```

Readable answers without jq:

```bash
naqsha run --profile workbench --human "what time is it?"
```

Inspect policy before enabling side effects (`--approve-prompt` / `auto_approve` in profiles):

```bash
naqsha profile show --profile workbench   # alias: inspect-policy
naqsha tools list --profile workbench
```

Latest trace shorthand:

```bash
naqsha replay --profile workbench --latest --human
```

### CLI cheat sheet

| Command | Purpose |
|--------|---------|
| `naqsha init` | Create `.naqsha/` and default **`workbench`** profile |
| `naqsha run` | Execute query — JSON stdout by default; `--human` prints answer only |
| `naqsha replay [--latest] [RUN_ID]` | Summary; `--re-execute` for regression replay |
| `naqsha trace inspect` | Same as replay summary mode |
| `naqsha inspect-policy` / `profile show` | Resolved profile + Tool Policy JSON |
| `naqsha tools list` | Tools + risk metadata JSON |
| `naqsha eval save` / `eval check` | Regression fixtures under `.naqsha/evals/` |
| `naqsha reflect` / `improve` | Reflection Patch workspace (**human review** required) |

`naqsha --version` shows the wheel version. `python -m naqsha …` runs the same CLI.

### Library quick start

```python
from naqsha import AgentWorkbench

wb = AgentWorkbench.from_profile_spec("workbench")
result = wb.run("hello")

from naqsha import build_runtime
from naqsha.profiles import load_run_profile

runtime = build_runtime(load_run_profile("local-fake"))
runtime.run("ping")
```

## Install and develop

```bash
python -m pip install naqsha
naqsha run --profile local-fake "what time is it?"
```

Checkout:

```bash
uv sync --extra dev
uv run --extra dev pytest
uv run --extra dev ruff check .
```

## Profiles

- Bundled **`local-fake`** (no `.naqsha/` needed for smoke tests).
- Short names resolve from `.naqsha/profiles/`, `./profiles/`, `./examples/profiles/` (see `profiles.py`).
- **`memory`** / **`web`** extras in `pyproject.toml` are reserved; **SimpleMem-Cross** is enabled via Run Profile (`memory_adapter`).

## Architecture

- **`runtime.py`** — Core Runtime
- **`wiring.py`** — `build_runtime` / `build_trace_replay_runtime` / `inspect_policy_payload`
- **`workbench/`** — `AgentWorkbench` façade
- **`cli.py`** — argparse only
- **`protocols/`**, **`trace/`**, **`policy.py`**, **`reflection/`**, **`models/`**, **`memory/`**, **`tools/`**, **`profiles.py`**

Hosted services, MCP inside Core Runtime, and heavy multi-agent orchestration stay out of v1 scope.

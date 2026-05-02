# Live-network sandbox for NAQSHA

Full documentation lives in **[`docs/user-guide/`](../docs/user-guide/README.md)**—this folder is **only** for manual, billing-bearing checks.

Use this folder for **manual** checks against **real** Gemini APIs and starter tools.

**Costs money.** **Touches the network.** **`tool_root`** is `workspace/` (keep it disposable).

## Setup once

From the **repository root** (`naqsha` checkout):

```bash
uv sync --extra dev
cd sandbox/live
export GEMINI_API_KEY="YOUR_KEY"
```

Optional: edit `profiles/gemini-live.json` → `gemini.model` for the exact model id you use (must work with Google AI `generateContent`).

### Optional: Gemini + SQLite memory Cross

Copy `profiles/gemini-live.json` to `profiles/gemini-live-memory.json` and set:

- `"memory_adapter": "simplemem_cross"`
- `"memory_cross_database": "../.naqsha/simplemem-cross.sqlite"`

### Why `--profile` must be absolute here

`uv run --directory /path/to/repo naqsha …` runs with **current working directory = repo root**, not `sandbox/live`. Relative paths like `profiles/gemini-live.json` resolve against the repo root and **miss** this folder. The script uses **absolute** profile paths; copy that pattern in your own commands.

## Run the scripted checklist

```bash
cd sandbox/live
export GEMINI_API_KEY="YOUR_KEY"

# Safe default (write/shell still blocked without --approve-prompt)
./run-live-checks.sh

# All Tool Policy capabilities that need approval (writes into workspace/, shell, etc.)
# Only use in this disposable folder and with an empty-ish workspace/.
./run-live-checks.sh full
```

The script refuses to run if `GEMINI_API_KEY` is empty.

## Approve gated tools safely

Profiles here use **`auto_approve`: false**. For **`run_shell`** / **`write_file`**, either:

```bash
uv run --directory ../.. naqsha run --profile profiles/gemini-live.json --approve-prompt "…"
```

or (only inside this throwaway `workspace/`):

```bash
uv run --directory ../.. naqsha run --profile profiles/gemini-live.json --auto-approve "…"
```

## Automated live pytest (also costs API $)

Runs only when you opt in:

```bash
cd /path/to/repo
export GEMINI_API_KEY="YOUR_KEY"
NAQSHA_LIVE=1 uv run --extra dev pytest tests/live_network -v --tb=short
```

Default **`pytest`** (no env) skips these tests so CI stays offline.

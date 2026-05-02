# NAQSHA

NAQSHA is a minimal Python agent runtime whose core owns agent execution, trace events,
tool contracts, memory hooks, and runtime guardrails.

The public project name, PyPI distribution, import package, and CLI command are all
`naqsha`.

## Current Status

This repository is scaffolded around the v1 Runtime Slice described in
`docs/prd/0001-naqsha-v1-runtime.md`. The code is intentionally small but not demo-shaped:
the module boundaries are meant to let future agents add real adapters without changing
the Core Runtime semantics.

Implemented in the scaffold:

- strict NAP message dataclasses and validation helpers
- QAOA trace event dataclasses and append-only JSONL trace store
- Core Runtime loop with fake model support, tool policy, approvals, budgets, scheduler,
  sanitizer, memory port hooks, and replay helpers
- starter tools for calculator, clock, read file, write file, shell placeholder, web
  placeholders, JSON patch placeholder, and human approval
- CLI with bundled `local-fake` Run Profile and JSON/TOML profile files
- deterministic tests for the first Runtime Slice contracts

Deliberately deferred:

- live provider adapters
- full SimpleMem-Cross integration
- hosted services, MCP adapters, UI, heavy planners, and multi-agent orchestration
- automatic Reflection Patch generation beyond the isolated interfaces

## Quick Start

```bash
uv sync --extra dev
uv run pytest
uv run naqsha run --profile local-fake "what time is it?"
```

Without `uv`, use any Python 3.11+ environment:

```bash
python -m pip install -e ".[dev]"
pytest
naqsha run --profile local-fake "what time is it?"
```

## Architecture Map

- `src/naqsha/runtime.py` is the Core Runtime.
- `src/naqsha/protocols/nap.py` owns NAP Action validation.
- `src/naqsha/protocols/qaoa.py` owns Query, Action, Observation, Answer, and Failure trace events.
- `src/naqsha/trace/jsonl.py` owns append-only JSONL trace persistence.
- `src/naqsha/policy.py` owns Tool Policy and Approval Gate decisions.
- `src/naqsha/scheduler.py` owns conservative serial/parallel tool execution.
- `src/naqsha/budgets.py` owns hard runtime caps.
- `src/naqsha/sanitizer.py` owns observation redaction and truncation.
- `src/naqsha/memory/` owns Memory Port contracts and local fakes/stubs.
- `src/naqsha/models/` owns Model Client ports and deterministic fake clients.
- `src/naqsha/tools/` owns tool contracts and Starter Tool Set.
- `src/naqsha/profiles.py` owns Run Profile parsing plus bundled profiles under `bundled_profiles/`.
- `src/naqsha/cli.py` wires the CLI into adapters and invokes the Core Runtime.
- `src/naqsha/reflection/` owns Reflection Loop boundaries.

## Development Rule

Do not put provider-specific response formats, hosted service assumptions, MCP behavior,
or SimpleMem-Cross internals into `CoreRuntime`. Add those behind ports/adapters.

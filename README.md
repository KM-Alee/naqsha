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

Implemented in v1 scope:

- strict NAP message dataclasses and validation helpers
- QAOA trace event dataclasses and append-only JSONL trace store
- Core Runtime loop with fake and remote model adapters, tool policy, approvals, budgets,
  scheduler, sanitizer, Memory Port hooks, trace replay, and **Reflection Loop** artifacts
- Starter Tool Set (calculator, clock, filesystem, shell, web fetch/search, JSON Patch,
  human approval, and related policy metadata)
- CLI with bundled `local-fake` Run Profile and JSON/TOML profile files
- optional **SimpleMem-Cross** SQLite adapter and OpenAI-compatible, Anthropic, and Gemini
  model clients (profile-driven; secrets via environment variable **names** only)

Deliberately out of v1 release scope:

- hosted services, bundled MCP, product UI, heavy planners, and multi-agent orchestration

## Quick Start

```bash
uv sync --extra dev
uv run --extra dev pytest
uv run --extra dev ruff check .
uv run naqsha run --profile local-fake "what time is it?"
```

Install from PyPI (or a local wheel) without the dev extra:

```bash
python -m pip install naqsha
naqsha run --profile local-fake "what time is it?"
```

With a checkout and editable dev install:

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

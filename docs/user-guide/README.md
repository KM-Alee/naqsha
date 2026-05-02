# NAQSHA user documentation

NAQSHA is a Python **Core Runtime** and **Agent Workbench** for running tool-using agents with strict **NAP Actions**, append-only **QAOA Traces**, enforced **Tool Policy**, optional **Approval Gates**, and a pluggable **Memory Port**. The PyPI package, import name, and CLI are `naqsha`.

This directory is the hub for practical guides. For authoritative vocabulary and relationships between terms, see the project glossary in [CONTEXT.md](../../CONTEXT.md).

## Who this is for

| Audience | What you get here |
|----------|-------------------|
| **Application developers** | A stable CLI and library surface to run agents, inspect **QAOA Traces**, and wire **Run Profiles** without treating provider chat logs as the source of truth. |
| **Runtime and safety engineers** | Explicit **Tool Policy**, **Approval Gate**, and trace semantics you can reason about outside the model prompt. |
| **Contributors** | Same commands as users, plus the repository’s `uv` dev workflow in the [README.md](../../README.md). |

## Table of contents

| Guide | Description |
|-------|-------------|
| [Getting started](./01-getting-started.md) | Install, `naqsha init`, first **`workbench`** run, JSON vs `--human`, **run_id**, replay, and smoke runs with bundled **`local-fake`**. |
| [Architecture & concepts](./02-architecture-and-concepts.md) | **Core Runtime** boundaries, **NAP Actions**, **QAOA Traces**, scheduling, sanitizer, budgets, **Memory Port**. |
| [Run Profiles & CLI](./03-run-profiles-and-cli.md) | Profile resolution, every field and flag, **Tool Policy**, **Approval Gate**, credential hygiene. |
| [Library, eval & reflection](./04-library-traces-eval-and-reflection.md) | **`AgentWorkbench`**, `build_runtime`, replay-by-**call id**, eval fixtures, **Reflection Patches** (review-only). |

## Quick install

```bash
python -m pip install naqsha
```

Verify:

```bash
naqsha --version
```

Equivalent: `python -m naqsha --version`.

## Related material

- **[CONTEXT.md](../../CONTEXT.md)** — Glossary: NAQSHA, Core Runtime, Agent Workbench, **QAOA Trace**, **NAP Action**, **Memory Port**, **Tool Policy**, **Approval Gate**, **Run Profile**, and related terms (use these names in docs and issues).
- **[examples/profiles/README.md](../../examples/profiles/README.md)** — Example **Run Profile** JSON, remote model adapters, and path resolution rules.
- **[README.md](../../README.md)** — Project overview, cheat sheet, and library quick start.
- **Design record** — [Architecture decisions](../adr/) (`docs/adr/`) when you need rationale beyond how-to guides.

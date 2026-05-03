# NAQSHA

**NAQSHA** is a minimal, production-shaped **Python agent runtime** — not a thin wrapper around a chat API.

It gives you a headless **Core Runtime** with enforced **Tool Policy**, append-only **Hierarchical QAOA Traces**, explicit **Approval Gates**, a **Dynamic Memory Engine**, **multi-agent Team Workspaces** with Tool-Based Delegation, autonomous **Reflection Patches** with a Reliability Gate, and a rich **Workbench TUI**.

Every design decision is captured in an Architecture Decision Record. Every safety invariant is runtime-enforced, not prompt-based.

---

## What makes NAQSHA different

| Problem | NAQSHA's answer |
|---|---|
| Auditable records | Append-only **QAOA Trace** — not an API chat log |
| Safety enforcement | **Tool Policy** + **Approval Gates** at runtime, not in prompts |
| Untrusted tool output | **Observation Sanitizer** runs before traces, memory, and prompts see payloads |
| Regression testing | Deterministic **trace replay** against recorded `call_id`-indexed observations |
| Multi-agent coordination | Auto-generated `delegate_to_<worker>` tools — no graph engine required |
| Cost control | **Budget Limits** fail closed — steps, tokens, tool calls, wall time |
| Runaway protection | **Circuit Breaker** trips on repeated identical failures; clean escalation to orchestrator |
| Autonomous improvement | **Reflection Loop** with mandatory **Reliability Gate** before any merge |

---

## Quick links

- **[Install and first run →](getting-started.md)**
- **[V2 vocabulary and architecture →](concepts.md)**
- **[Define tools with `@agent.tool` →](tools.md)**
- **[Multi-agent `naqsha.toml` teams →](teams.md)**
- **[Dynamic Memory Engine →](memory.md)**
- **[Reflection Loop and Rollback Manager →](reflection.md)**
- **[CLI and Workbench TUI →](cli.md)**
- **[API reference →](reference/index.md)**

---

## Version

This documentation covers **NAQSHA 0.2.0**.

Install: `pip install naqsha` · [PyPI](https://pypi.org/project/naqsha/) · [GitHub](https://github.com/KM-Alee/naqsha) · [Changelog](https://github.com/KM-Alee/naqsha/blob/main/CHANGELOG.md)

---

## Repository layout (top-level)

| Path | Contents |
|---|---|
| `src/naqsha/` | All runtime code: `core/`, `models/`, `tools/`, `memory/`, `orchestration/`, `tracing/`, `reflection/`, `tui/` |
| `docs/` | This documentation site |
| `docs/adr/` | Architecture Decision Records (0001–0019) |
| `docs/prd/` | Product Requirements Documents |
| `examples/` | Copy-paste `naqsha.toml` and Run Profile starters |
| `tests/` | Deterministic test suite (fake models; no API keys) |
| `naqsha.toml` | Reference Team Workspace configuration |

Design records live in `docs/adr/` and `docs/prd/`; they are excluded from this built site but are readable on [GitHub](https://github.com/KM-Alee/naqsha/tree/main/docs/adr). The canonical glossary is [CONTEXT.md](https://github.com/KM-Alee/naqsha/blob/main/CONTEXT.md).

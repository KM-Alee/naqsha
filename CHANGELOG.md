# Changelog

All notable changes to NAQSHA are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.2.0] — 2026-05-03

This is the **V2 feature release** of NAQSHA. It delivers a complete rewrite of the package internals under a domain-driven `src/` layout while preserving all V1 public imports. All ten V2 phases are complete and verified.

### Added

#### Core Runtime (`naqsha.core`)
- **Typed Event Bus** (`RuntimeEventBus`) — Pydantic-typed events (`RunStarted`, `RunCompleted`, `RunFailed`, `ToolInvoked`, `ToolCompleted`, `ToolErrored`, `SpanOpened`, `SpanClosed`, `AgentActivated`, `StreamChunkReceived`, `BudgetProgress`, `CircuitBreakerTripped`, `PatchMerged`, `PatchRolledBack`) emitted throughout the run loop.
- **Circuit Breaker** (`core/circuit_breaker.py`) — consecutive identical failure tracking per tool; configurable `max_retries` threshold; emits `CircuitBreakerTripped`; disabled during trace replay.
- **Budget Meter** improvements — `BudgetProgress` events emitted after each step and tool execution; hard caps fail closed on steps, tokens, tool calls, and wall-clock time.
- **Approval Gate** implementations — `StaticApprovalGate` and `InteractiveApprovalGate` in `core/approvals.py`.

#### Decorator-Driven API (`naqsha.tools`)
- **`@agent.tool` decorator** — generates JSON Schema Draft 2020-12 from type hints at import time; supports `str`, `int`, `float`, `bool`, `Optional[T]`, `list[T]`, `dict[str, T]`, Pydantic `BaseModel`, and `async def`; raises `ToolDefinitionError` on malformed signatures.
- **`ToolRegistry`** — holds decorated tools, supports lookup by name, exports schemas.
- **`ToolExecutor`** — auto-injects `AgentContext`, runs sync and async tools, normalizes all return types to `ToolObservation`.
- **`AgentContext`** — stable public API surface for tool authors; provides `shared_memory`, `private_memory`, `span`, `workspace_path`, `agent_id`, `run_id`.
- **`decorated_to_function_tool`** — bridges `@agent.tool` functions to legacy `FunctionTool` for `build_runtime` profiles.
- **Memory Schema Tool** (`memory_schema`, `list_memory_tables`) — DDL-safe schema evolution tools for agents.

#### Hierarchical QAOA Trace (`naqsha.tracing`)
- **V2 trace schema** — all events carry `trace_id`, `span_id`, `parent_span_id`, `agent_id`; `QAOA_TRACE_SCHEMA_VERSION = 2`; V1 traces auto-upgraded on load.
- **`SpanContext`** — immutable; propagated through execution trees; `child_span()` for delegation.
- **`Span`** — mutable; accumulates `token_count`, `model_latency_ms`, `tool_exec_ms`.
- **`TraceStore`** — reads V1 and V2; writes V2 only.

#### Dynamic Memory Engine (`naqsha.memory`)
- **`DynamicMemoryEngine`** — SQLite (WAL mode, `check_same_thread=False`), optional `sqlite-vec` embedding support.
- **`MemoryScope`** — enforces `shared_` and `private_<agent_id>_` namespace prefixes at the SQL level; other agents cannot access another agent's private tables.
- **DDL safelist** (`memory/ddl.py`) — permits `CREATE TABLE`, `CREATE INDEX`, `ALTER TABLE ADD COLUMN`; all other DDL raises `ForbiddenDDLError`.
- **`MemoryRetriever`** — token-budgeted retrieval with keyword + recency ranking (`keyword_hits * 1_000_000 + created_ts`); results wrapped as Untrusted Observations with provenance markers.
- **`TeamMemoryConfig` / `open_team_memory_engine`** — single team-wide SQLite file shared by all agents.

#### Multi-Agent Teams (`naqsha.orchestration`)
- **`TeamTopology`** — parsed from `naqsha.toml`; validates adapters, tool lists, Role-Based Tool Policy names; auto-injects `delegate_to_<worker>` tools for the orchestrator.
- **`build_team_orchestrator_runtime`** — orchestrator Core Runtime with delegation tools and shared memory.
- **Tool-Based Delegation** — `build_delegate_tool` runs a nested worker `CoreRuntime` under a child `SpanContext`; worker `AgentContext` is never exposed to the orchestrator.
- **Role-Based Tool Policy** — each agent in `naqsha.toml` has a strict allowlist; denials emit `ToolErrored` on the bus.

#### NAP V2 Model Adapters (`naqsha.models`)
- **`NapAction` / `NapAnswer`** — optional `span_context` field for hierarchical tracing.
- **Ollama adapter** (`models/ollama.py`) — `/api/chat` with tool-calling; `base_url` override; no live network in tests.
- All adapters (OpenAI-compatible, Anthropic, Gemini, Ollama, Fake) produce valid NAP V2 with `SpanContext` attached.
- `models/__init__.py` uses PEP 562 lazy `__getattr__` to prevent circular imports.

#### Reflection Loop V2 (`naqsha.reflection`)
- **`AutomatedRollbackManager`** — snapshots workspace before autonomous merges; restores on failed boot probe; prunes to 5 backups.
- **`ReflectionTomlSettings`** — loads `[reflection]` from `naqsha.toml`; `auto_merge` defaults to `false`.
- **`ReflectionPatchEventSink`** protocol — bridges reflection events to `RuntimeEventBus` without importing `core/`.
- Auto-merge requires Reliability Gate pass; there is no bypass.

#### Workbench TUI (`naqsha.tui`)
- **`WorkbenchApp`** — Textual-based TUI; subscribes to `RuntimeEventBus`; `tokyo-night` theme; `call_from_thread` safe.
- **`ChatPanel`** — streaming token display; `StreamChunkReceived` events.
- **`BudgetPanel`** — live step/tool/wall-clock progress bars from `BudgetProgress`.
- **`SpanTreePanel`** — expandable trace tree from `SpanOpened`/`SpanClosed`.
- **`FlamePanel`** — per-agent wall time and token totals from span events.
- **`MemoryBrowserPanel`** — read-only SQLite table viewer.
- **`PatchReviewPanel`** — diff view with Approve/Reject for Reflection Patches.
- **`naqsha init` wizard** (`InitWizardApp`) — interactive `naqsha.toml` generator.
- `NAQSHA_NO_TUI=1` environment variable forces plain output.

#### Documentation
- Full MkDocs-Material site under `docs/`: getting-started, concepts, tools, teams, memory, reflection, CLI, migration, API reference.
- Auto-generated API reference from docstrings for all eight domain packages.
- `mkdocs build --strict` runs in CI on Python 3.11 and 3.12.
- **GitHub Pages** deployment via `docs.yml` workflow at `https://km-alee.github.io/naqsha/`.

### Changed

- **Domain-Driven `src/` layout** — all modules reorganized into `core/`, `models/`, `tools/`, `memory/`, `orchestration/`, `tracing/`, `reflection/`, `tui/`; V1 import paths preserved via shims.
- **`pyproject.toml`** — version `0.2.0`; richer description and keywords; `Documentation` URL points to GitHub Pages; `Changelog` URL added.
- **`naqsha/__init__.py`** — `__version__ = "0.2.0"` exported; full V2 public API re-exports.
- **CI** (`ci.yml`) — adds `mkdocs build --strict`; separate `docs.yml` for GitHub Pages deployment.

### Fixed

- Pydantic 2.0+ compatibility throughout all event models and trace types.
- `sqlite3` `check_same_thread=False` for multi-threaded tool execution.
- V1 trace backward compatibility — old traces without `span_id` auto-upgrade on load.

### Security

- **Observation Sanitizer** runs before every trace write, memory write, and model context injection — no raw tool output bypasses sanitization.
- **Budget Limits** fail closed — exhausted budgets produce structured failures, not soft warnings.
- **DDL safelist** enforced at the SQL level — `DROP TABLE`, `DELETE`, `TRUNCATE` via Memory Schema Tool are always rejected.
- Private memory namespaces (`private_<agent_id>_`) are inaccessible to other agents at the SQL level.
- Credentials must be environment variable names in config files; secret values are never stored in `naqsha.toml` or profile files.

---

## [0.1.0] — 2025-11-01

Initial public release.

### Added
- `CoreRuntime` — ReAct loop with NAP V1 protocol.
- `FunctionTool` and Starter Tool Set (clock, list_files, read_file, web_search stub, …).
- `ToolPolicy` — allow/deny lists with risk tier gating.
- `ApprovalGate` — blocking human approval for `write`-tier tools.
- `BudgetMeter` — hard caps on steps, tokens, and tool calls.
- `ObservationSanitizer` — redacts secret-like content before trace/memory.
- `JsonlTraceStore` — append-only QAOA trace (V1 schema).
- `SimpleMem-Cross` adapter — default local SQLite memory.
- `TraceReplayModelClient` — deterministic replay from recorded observations.
- `naqsha run`, `naqsha replay`, `naqsha eval`, `naqsha reflect` CLI.
- `AgentWorkbench` façade for library embedders.
- JSON and TOML Run Profile support.
- MIT license.

[0.2.0]: https://github.com/KM-Alee/naqsha/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/KM-Alee/naqsha/releases/tag/v0.1.0

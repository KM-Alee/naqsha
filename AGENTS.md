# Agent Development Guide

Read these files first, in order:

1. `CONTEXT.md`
2. `docs/prd/0002-naqsha-v2-runtime.md`
3. All ADRs in `docs/adr/` (ADRs 0001–0005 are V1 history; ADRs 0006–0019 define V2 architecture)
4. `docs/handoff/0002-v2-development-workflow.md`
5. This file
6. `README.md`

## Non-Negotiable Vocabulary

Use the glossary in `CONTEXT.md` at all times. Key V2 terms:

- Say **NAQSHA**, not NAQSH.
- Say **Core Runtime**, not platform or app.
- Say **Team Workspace**, not agent folder or agent workspace.
- Say **Hierarchical QAOA Trace**, not flat trace or provider transcript.
- Say **NAP Action** (V2), not free-form model instruction.
- Say **Dynamic Memory Engine**, not chat history or SimpleMem.
- Say **Typed Event Bus**, not print statements or logging.
- Say **Decorator-Driven API**, not class-based tools.
- Say **Tool-Based Delegation Model**, not graph routing or state machine.
- Say **Automated Rollback Manager**, not undo or git revert.
- Say **Workbench TUI**, not dashboard or web UI.
- Say **Role-Based Tool Policy**, not per-agent permissions.
- Say **Circuit Breaker**, not retry limit or error handler.
- Say **Tool Policy** and **Approval Gate**, not prompt-only safety.

## V2 Module Ownership

These boundaries must be preserved. Every agent must know them before making changes.

### `src/naqsha/core/`
Owns the headless execution engine.
- `core/runtime.py` — orchestrates the agent run loop.
- `core/events.py` — all Pydantic event models for the Typed Event Bus.
- `core/event_bus.py` — `RuntimeEventBus`: subscribe, emit, async generator.
- `core/policy.py` — Tool Policy: allow, deny, approval requirements.
- `core/scheduler.py` — serial vs. parallel execution, per-tool timeouts.
- `core/circuit_breaker.py` — Circuit Breaker: consecutive failure tracking.
- `core/budgets.py` — `BudgetMeter`: hard caps for steps, tokens, tool calls, wall-clock time.
- `core/approvals.py` — Approval Gate implementations (`StaticApprovalGate`, `InteractiveApprovalGate`).

**Critical constraint:** `core/` must NEVER import from `tui/`. The core is headless.

**Phase 4 guidance (team runs):**
- `RuntimeConfig` carries `agent_id`, `workspace_path`, optional `span_context`, and optional `MemoryScope` fields (`shared_memory_scope`, `private_memory_scope`) in addition to legacy `memory` (`MemoryPort`).
- Each `run()` establishes or reuses a `SpanContext`, writes V2 trace attribution (`trace_id`, `span_id`, `parent_span_id`, `agent_id`) on persisted events, and emits `SpanOpened` / `SpanClosed` on the bus when `event_bus` is set.
- Tool Policy denials emit `ToolErrored` on the bus (in addition to the persisted denial observation).

### `src/naqsha/models/`
Owns provider translation. The Core Runtime only speaks NAP V2.
- `models/nap.py` — NAP V2 protocol definitions (`NAPAction`, `NAPAnswer`, `SpanContext`).
- `models/factory.py` — `model_client_from_profile`.
- `models/trace_turns.py` — Hierarchical QAOA Trace → neutral provider transcript.
- `models/http_json.py` — JSON POST, HTTP error handling, header redaction.
- `models/errors.py` — `ModelInvocationError`.
- `models/openai_compat.py`, `models/anthropic.py`, `models/gemini.py`, `models/ollama.py` — Thin Adapters.
- `models/trace_replay.py` — `TraceReplayModelClient` for deterministic replay.

**Phase 6 guidance:**
- NAP V2 types live in `models/nap.py` (`NapAction`, `NapAnswer`, optional `span_context: SpanContext | None`). `tracing/protocols/nap.py` and `protocols/nap.py` re-export from there.
- `ModelClient.next_message(..., span_context: SpanContext | None = None)` — Thin Adapters attach the active span to returned messages via `attach_span_context`.
- `models/__init__.py` uses PEP 562 lazy `__getattr__` so importing `naqsha.models.nap` does not eagerly import `factory`/`profiles` (breaks circular imports with `profiles` ↔ `protocols.nap`).

**Invariant:** Provider-specific formats must never appear outside the adapter files. No `if provider == "openai"` in `core/`.

### `src/naqsha/tools/`
Owns the Decorator-Driven API, schema generation, and execution.
- `tools/decorator.py` — `@agent.tool` decorator. Generates `__tool_schema__` on decoration.
- `tools/registry.py` — `ToolRegistry`: holds tools, exports schemas.
- `tools/executor.py` — `ToolExecutor`: resolves `AgentContext` injection, catches exceptions, returns `ToolErrorObservation` on failure.
- `tools/context.py` — `AgentContext`: the stable public API for tool authors.
- `tools/starter.py` — the V2 Starter Tool Set (all defined with `@agent.tool`).
- `tools/http_utils.py` — stdlib HTTP helpers.
- `tools/json_patch.py` — RFC 6902 JSON Patch helpers.
- `tools/decorated_adapter.py` — `decorated_to_function_tool`: bridges `@agent.tool` functions to `FunctionTool` for Core Runtime wiring.

**Invariant:** `AgentContext` is the only way for tools to access runtime state. No global variables in tools.

**Phase 1 guidance:**
- The `@agent.tool` decorator uses `inspect.signature` and `typing.get_type_hints` to generate JSON Schema Draft 2020-12 at decoration time.
- Supported type hints: `str`, `int`, `float`, `bool`, `Optional[T]`, `list[T]`, `dict[str, T]`, Pydantic `BaseModel` subclasses.
- Parameters with type hint `AgentContext` are automatically injected at runtime and omitted from the public schema.
- The decorator raises `ToolDefinitionError` at decoration time (not runtime) for malformed signatures.
- `ToolExecutor.execute()` handles both sync and async tools. For async tools, it returns a coroutine that must be awaited.
- `ToolExecutor.execute()` uses `get_type_hints()` to detect `AgentContext` parameters (annotation identity alone is not enough for all loader paths).
- Tools can return `str`, `dict`, `ToolObservation`, or any other type (converted to string). The executor normalizes all to `ToolObservation`.

### `src/naqsha/memory/`
Owns the Dynamic Memory Engine.
- `memory/engine.py` — `DynamicMemoryEngine`: SQLite + optional sqlite-vec.
- `memory/scope.py` — `MemoryScope`: enforces `shared_` and `private_<agent_id>_` namespace prefixes at SQL level.
- `memory/ddl.py` — DDL safelist enforcement: only `CREATE TABLE`, `CREATE INDEX`, `ALTER TABLE ADD COLUMN` permitted.
- `memory/retrieval.py` — token-budgeted retrieval with keyword + recency + optional semantic ranking.

**Invariant:** The `private_<agent_id>_` namespace is never accessible to other agents, even via `AgentContext.shared_memory`.

**Phase 3 guidance:**
- The DDL safelist applies only to schema-changing operations (CREATE, ALTER, DROP). Regular DML (INSERT, SELECT, UPDATE, DELETE) is permitted for normal memory operations.
- MemoryScope automatically prefixes table names with the namespace. Tools and agents work with logical table names; the scope handles physical prefixing.
- The ranking formula for retrieval is `(keyword_hits * 1000000) + created_ts` to ensure keyword matches dominate over recency.
- All memory operations should go through MemoryScope, not direct SQLite connection access.
- The Memory Schema Tool (`memory_schema`) validates DDL before execution to provide clear error messages to agents.
- `memory/sharing.py` — `TeamMemoryConfig` / `open_team_memory_engine`: one team-wide SQLite file; all agents share the `shared_` namespace and distinct `private_<agent_id>_` namespaces.
- `DynamicMemoryEngine` opens SQLite with `check_same_thread=False` so tools invoked from `ToolScheduler`'s thread pool can use the same connection safely (see Python ``sqlite3`` notes on multi-threading).

### `src/naqsha/orchestration/`
Owns Team Workspace topology and Tool-Based Delegation.
- `orchestration/topology.py` — `TeamTopology` parsed from `naqsha.toml` (`[workspace]`, `[agents.*]`, `[memory]`, `[reflection]`). Validates model adapters, non-empty tool lists, and Role-Based Tool Policy names; auto-injects `delegate_to_<worker>` tools for the orchestrator.
- `orchestration/delegation.py` — `build_delegate_tool(...)`: runs a nested worker `CoreRuntime` under a child `SpanContext`; never passes the orchestrator `AgentContext`.
- `orchestration/team_runtime.py` — `build_team_orchestrator_runtime`, `build_worker_runtime`, and `run_profile_for_topology_agent` (bridges `AgentRoleConfig` → `RunProfile` for model wiring).

**Invariant:** The Orchestrator's `AgentContext` is never passed to a worker. Worker isolation is absolute.

**Phase 4 guidance:**
- Use `build_team_orchestrator_runtime(topology, workspace_path, event_bus=...)` for multi-agent teams; single-agent `build_runtime(profile)` remains unchanged.
- Worker's trace events share the orchestrator `run_id` and trace file; `agent_id` and `parent_span_id` distinguish hierarchy.

**Phase 5 guidance:**
- `RuntimeConfig.max_retries` maps to the circuit breaker via `circuit_failure_threshold`: values `<= 0` trip on the first identical consecutive failure; otherwise the threshold is `max_retries` identical failures in a row for the same tool name.
- The breaker is disabled when `ToolScheduler.recorded_observations` is set (trace replay), so replays do not introduce new trips.
- Tool exceptions from decorated tools and uncaught `FunctionTool` raises both become failed `ToolObservation` with `metadata["error"]` and `metadata["tool_error"]=True` before trace write and bus emission.
- Worker failures from a tripped breaker return to the orchestrator as a failed delegation `ToolObservation` with `metadata["kind"]="TaskFailedError"` and `metadata["circuit_breaker"]=True` when applicable.

### `src/naqsha/tracing/`
Owns the Hierarchical QAOA Trace.
- `tracing/protocols/qaoa.py` — V2 trace event models. `QAOA_TRACE_SCHEMA_VERSION = 2`. `_SUPPORTED_SCHEMA_VERSIONS = {1, 2}`.
- `tracing/protocols/nap.py` — NAP V2 models (re-exported from `models/nap.py` for protocol consumers).
- `tracing/span.py` — `Span`, `SpanContext`, `create_root_span()`.
- `tracing/store.py` — `TraceStore`: append-only JSONL. Reads V1 and V2. Writes V2.
- `tracing/sanitizer.py` — `ObservationSanitizer`: runs before any trace write, memory write, or model context injection.
- `tracing/replay.py` — `nap_messages_from_trace`, `observations_by_call_id`, `compare_replay`.

**Schema versioning rule:** When changing the persisted trace shape, bump `QAOA_TRACE_SCHEMA_VERSION` and update `_SUPPORTED_SCHEMA_VERSIONS`. Never silently accept an unsupported version.

**Phase 2 guidance:**
- V2 trace events include `trace_id`, `span_id`, `parent_span_id`, `agent_id` for hierarchical tracing.
- V1 traces are automatically upgraded on load: missing `span_id` gets generated, `run_id` becomes `trace_id`, treated as root span.
- `TraceEvent.to_dict()` conditionally serializes V2 fields only when `schema_version >= 2` to maintain V1 compatibility.
- `SpanContext` is immutable and propagated through execution trees. Use `child_span()` to create child spans.
- `Span` is mutable and accumulates metrics (`token_count`, `model_latency_ms`, `tool_exec_ms`).
- All trace event helper functions accept optional span context parameters with empty string defaults for backward compatibility.

### `src/naqsha/reflection/`
Owns the Reflection Loop and Automated Rollback Manager.
- `reflection/loop.py` — `SimpleReflectionLoop`: reads `[reflection]` from `naqsha.toml` (via `reflection/config.py`) or injected settings; runs the Reliability Gate whenever `project_root` resolves; optional auto-merge after gate pass when TOML allows.
- `reflection/base.py` — `ReflectionPatch`: `ready_for_human_review`, `auto_merged`; `ReflectionPatchEventSink` protocol for embedders to forward to `RuntimeEventBus` (reflection never imports `core/`).
- `reflection/config.py` — `ReflectionTomlSettings`, `load_reflection_toml_settings`; `reliability_gate` gates **auto-merge** only (pytest still runs when `project_root` is set).
- `reflection/rollback.py` — `AutomatedRollbackManager`: snapshot, restore, boot-status lifecycle.
- `reflection/reliability_gate.py` — `run_reliability_gate_subprocess`: runs pytest over gate paths.
- `reflection/workspace.py` — `create_isolated_workspace`: rejects paths under the installed package tree.
- `reflection/candidate.py` — deterministic artifact generation.

**Invariants:**
- The `reflection/` package must NEVER import `core/`, `tools/`, or `core/policy.py` directly.
- Auto-merge requires Reliability Gate pass. There is no bypass.
- `auto_merge = false` is always the default in wizard-generated workspaces and all templates.

### `src/naqsha/tui/`
Owns the Workbench TUI.
- `tui/app.py` — `WorkbenchApp(textual.App)`: Chat, Budget, Span Tree, Flame, Memory browser, Patch review; subscribes to `RuntimeEventBus`.
- `tui/wizard/init.py` — `naqsha init` interactive wizard.
- `tui/panels/chat.py` — `ChatPanel`: streaming tokens.
- `tui/panels/budget.py` — `BudgetPanel`: live counters.
- `tui/panels/span_tree.py` — `SpanTreePanel`: expandable trace tree.
- `tui/panels/flame.py` — `FlamePanel`: time/token bar chart.
- `tui/panels/memory.py` — `MemoryBrowserPanel`: SQLite table viewer.
- `tui/panels/patch_review.py` — `PatchReviewPanel`: diff view with approve/reject.
- `tui/workbench.tcss` — Workbench layout, surfaces, and header/footer chrome (Phase 8+).
- `tui/wizard/wizard.tcss` — Init wizard card layout and typography.

**Invariant:** The `tui/` package is ONLY imported from `cli.py` and other `tui/` modules. All other packages must be importable without `textual` installed (it is an optional extra `[tui]`).

**Workbench visual standard (Phase 8 onward, non-negotiable):** Every new or changed TUI surface must ship **production-grade polish**: cohesive theme (Workbench defaults to **`tokyo-night`**), clear typographic hierarchy (titles, muted hints, accent for actions), generous spacing and padding, `tall` / `rounded` borders and `$surface` / `$boost` depth, readable Rich markup in logs and trees, and **`.tcss` files** colocated with the feature (`workbench.tcss`, per-panel `DEFAULT_CSS`, wizard styles). Phase 9+ panels (flame, memory, patch review) must meet the same bar—no bare placeholder layouts in mergeable work.

**Phase 8 guidance (Workbench TUI):**
- `WorkbenchApp` runs `CoreRuntime.run()` on a Textual worker thread; bus handlers use `call_from_thread` before mutating widgets (wired in `tui/app.py`). Default theme **`tokyo-night`**; panel `border_title`s identify each region.
- `BudgetPanel` listens for `BudgetProgress`; `ChatPanel` listens for `StreamChunkReceived` (Core Runtime chunks final answers for pseudo-streaming).
- Interactive `naqsha init` writes `naqsha.toml` via `InitWizardApp`; interactive `naqsha run` uses the same `RuntimeEventBus` instance as `build_runtime(..., event_bus=bus)` for live panels.

**Phase 9 guidance (advanced Workbench panels):**
- `FlamePanel` derives per-agent wall seconds from `SpanOpened` / `SpanClosed` timestamps and stacks `token_count` from closes; exposes `metrics_snapshot()` for tests.
- `MemoryBrowserPanel` reads `.naqsha/memory.db` under `RuntimeConfig.workspace_path` (or an injected `db_path`); DDL is not executed from the TUI.
- `PatchReviewPanel` lists `reflection-patch-*` dirs under `.naqsha/reflection-workspaces` (same default parent as `naqsha reflect`), previews text via `reflection.loop.read_patch_review_texts`, and routes **Approve** / **Reject** to `approve_patch` / `reject_patch` with `RuntimeBusReflectionSink` for `PatchMerged` events.

### `src/naqsha/` (Root)
- `__init__.py` — flat public API. Re-exports: `agent`, `tool`, `AgentContext`, `CoreRuntime`, `TeamTopology`, `RuntimeEventBus`, and key event models. This is what library users import.
- `cli.py` — argument parsing and dispatch only. Uses `wiring.py` and `AgentWorkbench`. Must not invent runtime semantics. Lazily imports `tui/` when `tui_available()` and stdin/stdout are TTYs; set `NAQSHA_NO_TUI=1` to force plain JSON/text output.
- `wiring.py` — `build_runtime(profile)`, `build_trace_replay_runtime(trace, profile)`. Library embedders import from here, not from `cli.py`.
- `profiles.py` — `naqsha.toml` and `.json` Run Profile parsing. Supports both V1 JSON profiles and V2 TOML workspace configs.
- `project.py` — `.naqsha/` filesystem layout helpers (`naqsha init` output path logic).
- `eval_fixtures.py` — schema-versioned regression fixture save/load.
- `trace_scan.py` — lists traces by mtime.
- `workbench/` — `AgentWorkbench` facade: profiles, replay, eval, reflection entry points. Never imports `cli.py`.

## Phase Workflow

Use `docs/handoff/0002-v2-development-workflow.md` as the V2 project execution plan. Each new chat session works on one phase only unless an earlier phase is already complete and verified.

At the start of a phase:
- Read all required docs listed at the top of this file.
- Confirm which phase is in scope.
- Identify the expected result and acceptance criteria for that phase.
- Prefer tests first when the behavior is contract-shaped.

At the end of a phase:
- Run `uv run --extra dev pytest` (must pass).
- Run `uv run --extra dev ruff check .` (must pass).
- Update `docs/handoff/0002-v2-development-workflow.md`: set the phase status, fill in "Delivered", and write "Risks the next phase inherits".
- Update this file when the phase reveals durable guidance future agents must keep.
- In the final response, state what changed, what was verified, and what the next phase inherits.

## V2 Safety Invariants (Non-Negotiable)

These must hold at every commit. A change that violates these is not done, even if tests pass.

1. **All tool output is an Untrusted Observation.** It can inform the model but cannot instruct the runtime.
2. **The Observation Sanitizer runs before every trace write, memory write, and model context injection.** No exception.
3. **Budget Limits fail closed.** Exhausted budgets produce structured failures, not warnings or soft stops.
4. **`auto_merge = false` is the default everywhere.** Opt-in only.
5. **The Reliability Gate is mandatory before any Reflection Patch merge**, whether auto or human.
6. **Worker isolation is absolute.** No `AgentContext` leaks from Orchestrator to Worker.
7. **`core/` never imports from `tui/`.**
8. **The DDL safelist is enforced.** `DROP TABLE`, `DELETE`, `UPDATE`, `TRUNCATE` via Memory Schema Tool are always rejected.
9. **Credentials are environment variable names in config files, never secret values.**
10. **Private memory namespaces are agent-scoped and inaccessible to other agents at the SQL level.**

## First Extension Tasks

Good scoped tasks for a less-capable agent:
- Add a new `@agent.tool`-decorated tool to `tools/starter.py` with tests.
- Expand the OWASP red-team corpus in `tests/redteam/` with multi-agent delegation injection scenarios.
- Add a new Model Adapter to `models/` for a new provider.
- Improve the Memory Schema Tool's DDL error messages for better developer UX.
- Add a new TUI panel (using an existing Textual widget) and wire it to a new event type.

## Things Not To Do

- Do not add `print()` statements to the `core/` package. Use the Typed Event Bus.
- Do not use global variables for tool state. Use `AgentContext`.
- Do not add `if provider == "openai"` logic outside of adapter files.
- Do not let Reflection Patches merge without the Reliability Gate passing.
- Do not default `auto_merge = true` in any template, wizard screen, or example profile.
- Do not import `tui/` from `core/`, `models/`, `tools/`, `memory/`, `orchestration/`, `tracing/`, or `reflection/`.
- Do not allow worker agents to read the Orchestrator's private memory.
- Do not persist private chain-of-thought in any trace event.
- Do not replace the Hierarchical QAOA Trace with provider-native chat transcripts.
- Do not make budgets advisory. Exhausted budgets fail closed.
- Do not store secret values (API keys, tokens) in `naqsha.toml` or profile files. Store environment variable names only.

## Packaging and Releases

The public PyPI distribution name, `import naqsha` package, and `naqsha` console script must remain `naqsha`.

- V2 version: `>=2.0.0`.
- Required Python: `>=3.11`.
- Optional extras: `[memory]` (sqlite-vec), `[tui]` (textual, rich), `[embeddings]` (sqlite-vec), `[dev]` (pytest, ruff, build, mkdocs stack).
- Typed package marker: `src/naqsha/py.typed`.
- CI: `.github/workflows/ci.yml` runs `uv sync --extra dev`, Ruff, full pytest, `mkdocs build --strict` on Python 3.11 and 3.12.
- Packaging smoke tests are optional; Phase 11 may reintroduce install checks under CI.
- Release checklist: `docs/release/pypi-checklist.md`.

## Completion Bar

A change is not done until it:
- Has deterministic tests with fake models/tools.
- Preserves append-only Hierarchical QAOA Trace behavior.
- Preserves runtime-enforced Tool Policy and Role-Based Tool Policies.
- Has the Observation Sanitizer running before trace, memory, and prompt reinjection.
- Uses explicit `naqsha.toml` choices instead of hidden environment-only config.
- Does not import `tui/` from any non-`tui/` package.
- Meets the **Workbench visual standard** for any shipped or changed TUI (see `tui/` section above).
- Passes `uv run --extra dev pytest` and `uv run --extra dev ruff check .`.

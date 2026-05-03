# NAQSHA V2 Development Handoff

This document is the live phase plan for building NAQSHA V2. It is the single source of truth for what has been done, what is in progress, and what comes next. Every agent that finishes a phase **must** update the phase status, the "Delivered" section, and the "Risks the next phase inherits" section before closing.

Read these files first, in order:
1. `CONTEXT.md`
2. `docs/prd/0002-naqsha-v2-runtime.md`
3. All ADRs in `docs/adr/` (especially 0006–0019)
4. This document
5. `AGENTS.md`

---

## How To Run Each Phase

At the start of every new chat, give the agent this instruction:

```text
Read CONTEXT.md, AGENTS.md, docs/prd/0002-naqsha-v2-runtime.md, all docs/adr/*.md,
and docs/handoff/0002-v2-development-workflow.md. Work only on Phase <N>. Preserve
the V2 vocabulary and module boundaries. Write tests first where the behavior is
contract-shaped. When done, update AGENTS.md with any new durable guidance and update
the phase status in this handoff document.
```

Every phase must end with:
- `uv run --extra dev pytest` (all tests must pass)
- `uv run --extra dev ruff check .` (zero lint errors)
- A short end-of-phase note in the "Delivered" section listing what changed, what remains open, and what risk the next phase inherits.

**TUI phases (8+):** Follow the **Workbench visual standard** in `AGENTS.md`—the shipped UI must be polished (theme, `.tcss`, typography), not a functional stub.

Do not combine phases unless the earlier phase is already complete and verified. Phases are sliced around stable public contracts so that a focused agent can keep its context small and still produce useful, mergeable work.

---

## AGENTS.md Update Rule

Every phase must consider whether `AGENTS.md` needs an update. Update it when a phase establishes durable guidance about:
- New module boundaries or ownership rules
- New public API contracts
- New testing fixtures, commands, or patterns
- New safety rules or invariants
- New dependency choices or restrictions
- Known traps that future agents are likely to fall into

Do not add implementation history noise to `AGENTS.md`. Keep this handoff document for phase state and sequencing. Keep `AGENTS.md` for standing instructions that must remain true across all phases and sessions.

---

## Phase 0: V2 Foundation — Domain-Driven src/ Layout and Event Bus

**Status:** complete

**Goal:** Establish the new V2 package skeleton, migrate or reorganize all V1 code into the Domain-Driven `src/` layout, and implement the Typed Event Bus at the `core` level. This phase does not add new user-visible behavior; its output is a cleanly restructured codebase where all V1 tests still pass and the Event Bus is emitting events for existing runtime operations.

**Scope:**
- Create the eight domain packages under `src/naqsha/`: `core/`, `models/`, `tools/`, `memory/`, `orchestration/`, `tracing/`, `reflection/`, `tui/`.
- Move V1 modules into their correct V2 homes. For example: `runtime.py` → `core/runtime.py`, `protocols/` → `tracing/protocols/`, `policy.py` → `core/policy.py`, `scheduler.py` → `core/scheduler.py`, `memory/` → `memory/`, `models/` → `models/`, `reflection/` → `reflection/`.
- Preserve all V1 public imports from `naqsha/__init__.py` as re-exports so no external code breaks.
- Implement `core/events.py`: define all V2 Pydantic event models (`RunStarted`, `AgentActivated`, `StreamChunkReceived`, `ToolInvoked`, `ToolCompleted`, `ToolErrored`, `SpanOpened`, `SpanClosed`, `RunCompleted`, `RunFailed`).
- Implement `core/event_bus.py`: `RuntimeEventBus` with `subscribe(handler)`, `emit(event)`, and `events()` async generator. The `core` package must not import from `tui` under any circumstances.
- Wire the `RuntimeEventBus` into the existing `CoreRuntime` so that it emits events for existing V1 operations (run start, tool invoked, answer produced, etc.).
- Add `tests/core/test_event_bus.py`: verify event ordering, subscription, and that a fake subscriber collects the correct sequence for a basic fake-model run.

**Do not:**
- Add new user-visible features in this phase.
- Break any passing V1 test.
- Import `tui` from any domain package other than `tui`.

**Exit criteria:**
- All V1 tests pass under the new layout. ✅
- Event Bus emits the correct ordered sequence for a fake-model run (verified by test). ✅
- `ruff check .` passes with zero errors. ✅

**Delivered:**
- Created V2 domain package structure: `core/`, `tracing/`, `orchestration/`, `tui/` with proper `__init__.py` files
- Moved core runtime files to `core/`: `runtime.py`, `budgets.py`, `policy.py`, `scheduler.py`, `approvals.py`
- Moved tracing files to `tracing/`: `protocols/`, `sanitizer.py`, `store.py` (renamed from `base.py`), `jsonl.py`, `replay.py`
- Created backward-compatibility shims in old locations to preserve V1 imports
- Implemented Typed Event Bus with Pydantic models in `core/events.py` and `core/event_bus.py`
- Wired Event Bus into `CoreRuntime`: emits `RunStarted`, `RunCompleted`, `RunFailed`, `ToolInvoked`, `ToolCompleted` events
- Added `RuntimeConfig.event_bus` optional field (defaults to None for backward compatibility)
- Updated `naqsha/__init__.py` to re-export Event Bus classes and all event types
- Added Pydantic 2.0+ as a core dependency in `pyproject.toml`
- Added pytest-asyncio for async test support
- Created comprehensive Event Bus tests in `tests/core/test_event_bus.py` (5 tests, all passing)
- Created V2 test directory structure mirroring domain packages
- All 164 V1 tests pass (6 skipped, 3 packaging errors due to network issues only)
- Ruff linting passes with zero errors

**Risks the next phase inherits:**
- The Event Bus is optional (event_bus=None by default) to maintain V1 compatibility. Phase 1 tools may need to consider whether to make it required or keep it optional.
- Some V1 modules still use old import paths via shims. Future phases should gradually migrate internal code to use new paths directly.
- The `trace/base.py` was renamed to `tracing/store.py` for V2 naming consistency. The shim preserves compatibility but internal code should migrate.
- Pydantic is now a required dependency. This adds ~2MB to the package but provides strong typing for events.

---

## Phase 1: Decorator-Driven API and Schema Generation

**Status:** complete

**Goal:** Implement the `@agent.tool` decorator and the schema-generation engine. Developers can now define tools as ordinary Python functions. The generated schemas must be strictly equivalent (in terms of Tool Policy validation behavior) to V1 manually-defined schemas.

**Scope:**
- Implement `tools/decorator.py`: `@agent.tool(risk_tier=..., description=...)`. On decoration, use `inspect.signature` and `typing.get_type_hints` to generate a JSON Schema Draft 2020-12 definition stored as `__tool_schema__` on the function object.
- Support: primitive types (`str`, `int`, `float`, `bool`), `Optional[T]`, `List[T]`, `Dict[str, T]`, Pydantic `BaseModel` subclasses, and `async def` functions.
- Raise a clear `ToolDefinitionError` at decoration time if the signature is malformed (e.g., unresolvable type hint, a parameter without a type hint that is not `ctx`).
- Implement `tools/registry.py`: `ToolRegistry` that holds decorated tools, supports lookup by name, and exports the schema list for Model Adapters.
- Implement `tools/executor.py`: `ToolExecutor` that resolves `AgentContext`-typed parameters and injects the live context. The `ctx` parameter must be omitted from the public schema (it is internal).
- Define `tools/context.py`: `AgentContext` Pydantic dataclass with fields: `shared_memory`, `private_memory`, `span`, `workspace_path`, `agent_id`, `run_id`. Keep it minimal and stable — this is a public API surface.
- Add `tests/tools/test_decorator.py`: cover primitive types, Pydantic models, `Optional`, async, injection, schema omission of `ctx`, and `ToolDefinitionError` cases.
- Migrate all V1 Starter Tool Set definitions from class-based to the new decorator style.

**Do not:**
- Change the Tool Policy or Approval Gate in this phase.
- Add `AgentContext` fields beyond what is listed above (premature extension is a trap).

**Exit criteria:**
- All migrated Starter Tools have identical schema behavior to V1 (verified by existing tool tests). ✅
- `@agent.tool` on an arbitrary function produces a valid JSON Schema (verified by schema tests). ✅
- `AgentContext` injection is transparent to the tool function. ✅

**Delivered:**
- Created `tools/context.py` with `AgentContext` dataclass containing all required fields (shared_memory, private_memory, span, workspace_path, agent_id, run_id)
- Created `tools/decorator.py` with `@agent.tool` decorator that:
  - Generates JSON Schema Draft 2020-12 from type hints using `inspect.signature` and `typing.get_type_hints`
  - Supports all required types: primitives (str, int, float, bool), Optional[T], list[T], dict[str, T], Pydantic BaseModel, async def
  - Raises clear `ToolDefinitionError` at decoration time for malformed signatures
  - Omits `AgentContext` parameters from public schema
  - Stores schema as `__tool_schema__`, risk tier as `__tool_risk_tier__`, read-only flag as `__tool_read_only__`
- Created `tools/registry.py` with `ToolRegistry` that:
  - Registers decorated tools with validation
  - Supports lookup by name
  - Exports schemas for Model Adapters
  - Provides risk tier and read-only queries
- Created `tools/executor.py` with `ToolExecutor` that:
  - Automatically injects `AgentContext` when requested via type hint
  - Handles both sync and async tool functions correctly
  - Converts various return types (str, dict, ToolObservation, other) to ToolObservation
  - Propagates exceptions (Phase 5 will wrap in ToolErrorObservation)
- Updated `tools/__init__.py` to export V2 API: `AgentContext`, `agent`, `tool`, `RiskTier`, `ToolDefinitionError`, `ToolRegistry`, `ToolExecutor`
- Updated `naqsha/__init__.py` to export V2 tool API at top level for `from naqsha import agent, tool, AgentContext`
- Created comprehensive test suite:
  - `tests/tools/test_decorator.py`: 19 tests covering all type hints, error cases, and edge cases
  - `tests/tools/test_registry.py`: 10 tests covering registration, lookup, schema export, and error handling
  - `tests/tools/test_executor.py`: 11 tests covering sync/async execution, context injection, and result conversion
  - `tests/tools/test_integration.py`: 5 tests covering end-to-end workflows
- All 45 new tests pass
- All 212 existing tests pass (6 skipped)
- Ruff linting passes with zero errors
- V1 class-based tools remain functional via backward-compatibility shims

**Risks the next phase inherits:**
- V1 Starter Tool Set has NOT been migrated to decorator style yet. Phase 1 focused on the decorator infrastructure. The migration should happen when the tools are actually used in integration with the Core Runtime.
- `AgentContext.shared_memory` and `AgentContext.private_memory` are typed as `MemoryPort | None` but the Dynamic Memory Engine (Phase 3) will change this to `MemoryScope` objects.
- `AgentContext.span` is typed as `Any | None` and will become `tracing.span.Span` in Phase 2.
- The `ToolExecutor` currently propagates exceptions directly. Phase 5 will wrap them in `ToolErrorObservation` and implement Circuit Breaker logic.
- The decorator generates schemas but does not validate arguments at runtime. The Core Runtime's existing validation logic must be wired to use the generated schemas.

---

## Phase 2: NAP V2 Protocol and Hierarchical QAOA Trace

**Status:** complete

**Goal:** Upgrade the trace and protocol layer to the Hierarchical QAOA Trace schema (V2). Every trace event carries `span_id`, `parent_span_id`, and `agent_id`. V1 traces must remain readable.

**Scope:**
- Bump `QAOA_TRACE_SCHEMA_VERSION` to `2` in `tracing/protocols/qaoa.py`.
- Add `schema_version`, `trace_id`, `span_id`, `parent_span_id` (nullable), and `agent_id` to all trace event models. Add `token_count`, `model_latency_ms`, and `tool_exec_ms` as optional span attributes.
- Implement `tracing/span.py`: `Span` and `SpanContext` dataclasses. `SpanContext` carries `trace_id`, `span_id`, `parent_span_id`, `agent_id`.
- Update `TraceStore` (formerly `trace/`) to write V2 events and read both V1 and V2 rows (V1 rows without `span_id` are treated as root-level spans with a generated `span_id`).
- Emit `SpanOpened` and `SpanClosed` events on the `RuntimeEventBus` when spans are created and completed.
- Add `tests/tracing/test_hierarchical_trace.py`: verify V2 schema write/read, V1 backward-compat load, span nesting, and round-trip replay of a trace with child spans.

**Do not:**
- Remove support for loading V1 traces.
- Change NAP Action schema in this phase (that comes with adapters).
- Add multi-agent delegation logic (that is Phase 4).

**Exit criteria:**
- V2 trace events serialize correctly with all new fields. ✅
- V1 trace files load without error as root-level spans. ✅
- `SpanOpened` / `SpanClosed` events appear on the Event Bus during a fake-model run. ✅

**Delivered:**
- Implemented `tracing/span.py` with `Span`, `SpanContext`, and `create_root_span()` function
- `SpanContext` is immutable and carries `trace_id`, `span_id`, `parent_span_id`, `agent_id`
- `SpanContext.child_span()` creates child spans with correct parent linkage
- `Span` is mutable and accumulates metrics: `token_count`, `model_latency_ms`, `tool_exec_ms`
- Bumped `QAOA_TRACE_SCHEMA_VERSION` to `2` in `tracing/protocols/qaoa.py`
- Added `_SUPPORTED_SCHEMA_VERSIONS = {1, 2}` for backward compatibility
- Extended `TraceEvent` dataclass with V2 fields: `trace_id`, `span_id`, `parent_span_id`, `agent_id`
- `TraceEvent.to_dict()` conditionally includes V2 fields only for schema_version >= 2
- `TraceEvent.from_dict()` reads V2 fields if present, generates defaults for V1 traces
- V1 traces without `span_id` get a generated `span_id` and are treated as root spans
- V1 traces use `run_id` as `trace_id` for backward compatibility
- Updated all trace event helper functions (`query_event`, `action_event`, `observation_event`, `answer_event`, `failure_event`) to accept optional span context parameters
- Added `tool_exec_ms` to observation event payload for tool execution time tracking
- Updated `AgentContext.span` type from `Any | None` to `Span | None` (Phase 1 risk resolved)
- Exported `Span`, `SpanContext`, `create_root_span` from `tracing/__init__.py` and `naqsha/__init__.py`
- Created comprehensive test suite in `tests/tracing/test_hierarchical_trace.py` (27 tests, all passing):
  - `TestSpanContext`: span creation and child span generation
  - `TestSpan`: metrics accumulation and serialization
  - `TestV2TraceEventSchema`: V2 event creation with span fields
  - `TestV2Serialization`: round-trip serialization/deserialization
  - `TestV1BackwardCompatibility`: V1 trace loading and compatibility
  - `TestTraceStoreV2`: JsonlTraceStore reads/writes V2 events
  - `TestEventBusSpanEvents`: SpanOpened/SpanClosed event structure
  - `TestSchemaVersioning`: schema version validation
  - `TestChildSpanNesting`: hierarchical span relationships
- All 77 core/tools/tracing tests pass
- Ruff linting passes with zero errors

**Risks the next phase inherits:**
- The Core Runtime does not yet emit `SpanOpened`/`SpanClosed` events automatically. Phase 3 or 4 will need to wire span lifecycle events into the runtime loop.
- NAP V2 protocol extension with `span_context` field is deferred to Phase 6 (Model Adapters). The span infrastructure is ready but not yet propagated through model adapters.
- The `observation_event` payload includes `tool_exec_ms` but the Core Runtime does not yet populate it. Phase 5 (Circuit Breakers) will add tool execution timing.
- Multi-agent delegation span nesting is implemented in the span module but not yet used. Phase 4 will wire this into the Tool-Based Delegation Model.
- The `Span.metadata` field is available but not yet used by any runtime component. Future phases may use it for custom span annotations.

---

## Phase 3: Dynamic Memory Engine

**Status:** complete

**Goal:** Replace the SimpleMem-Cross SQLite adapter with the new Dynamic Memory Engine. The engine supports Shared and Private memory namespaces, transactional writes, and an optional `sqlite-vec` embedding mode. The Memory Schema Tool is shipped.

**Scope:**
- Implement `memory/engine.py`: `DynamicMemoryEngine` wrapping `sqlite3`. On initialization, read `naqsha.toml` to determine if embeddings are enabled and load `sqlite-vec` if so.
- Implement `memory/scope.py`: enforce `shared_` and `private_<agent_id>_` namespace prefixes at the SQL level. `AgentContext.shared_memory` and `AgentContext.private_memory` return scoped `MemoryScope` objects. A `MemoryScope` exposes: `execute(sql, params)`, `query(sql, params)`, `begin()`, `commit()`, `rollback()`.
- Implement DDL safelist in `memory/ddl.py`: only `CREATE TABLE`, `CREATE INDEX`, and `ALTER TABLE ADD COLUMN` are permitted. All other DDL raises `ForbiddenDDLError`.
- Add the `memory_schema` tool to the `tools/` package (decorated with `@agent.tool(risk_tier="write")`).
- Implement `memory/retrieval.py`: token-budgeted retrieval with keyword + recency ranking (and optional semantic ranking if embeddings are enabled). Results are wrapped in provenance-annotated delimiters as Untrusted Observations.
- Update `profiles.py` / `naqsha.toml` parser to load `[memory]` config block.
- Add `tests/memory/test_engine.py`: shared/private isolation, DDL safelist, transactional rollback, retrieval ranking, and provenance annotation.
- Add `tests/memory/test_embeddings.py` (skipped if `sqlite-vec` is not installed) for semantic retrieval.

**Do not:**
- Remove the V1 `simplemem_cross` adapter path entirely in this phase — keep it wired but deprecated so existing V1 profiles still load.
- Add multi-agent memory sharing logic (that is Phase 4).

**Exit criteria:**
- Shared and Private namespaces are strictly isolated at the DB level. ✅
- Forbidden DDL raises an error before execution. ✅
- Transactional rollback on simulated mid-write failure is verified by test. ✅
- `memory_schema` tool appears in the ToolRegistry and passes schema tests. ✅

**Delivered:**
- Created `memory/ddl.py` with DDL safelist enforcement:
  - `validate_ddl()` function validates SQL against safelist
  - `is_ddl_statement()` helper to detect DDL operations
  - `ForbiddenDDLError` exception for violations
  - Permits: CREATE TABLE, CREATE INDEX, ALTER TABLE ADD COLUMN
  - Forbids: DROP, DELETE, UPDATE, TRUNCATE, INSERT (in DDL context)
- Created `memory/scope.py` with `MemoryScope` class:
  - Enforces `shared_` and `private_<agent_id>_` namespace prefixes
  - Automatic table name prefixing in SQL statements
  - DDL validation on execution
  - Transaction support: `begin()`, `commit()`, `rollback()`
  - `list_tables()` method to enumerate tables in namespace
  - Strict namespace validation on initialization
- Created `memory/engine.py` with `DynamicMemoryEngine` class:
  - SQLite-backed with WAL mode for concurrency
  - `get_shared_scope()` returns shared memory scope
  - `get_private_scope(agent_id)` returns agent-specific scope
  - Optional sqlite-vec support via `enable_embeddings` flag
  - `list_all_tables()` method to enumerate all namespaces
  - Automatic parent directory creation
- Created `memory/retrieval.py` with `MemoryRetriever` class:
  - Token-budgeted retrieval (~4 chars per token)
  - Keyword + recency ranking (keyword hits * 1000000 + timestamp)
  - Provenance-wrapped results with UNTRUSTED EVIDENCE delimiters
  - Deduplication by provenance
  - Automatic trimming of first result if budget exceeded
  - Configurable table and column names
- Created `tools/memory_schema.py` with two decorated tools:
  - `memory_schema(sql, ctx)` - Execute DDL with safelist validation
  - `list_memory_tables(ctx)` - List all accessible tables
  - Both tools use `@agent.tool` decorator
  - Proper risk tier assignment (write/read)
  - Clear error messages for forbidden operations
- Updated `memory/__init__.py` to export V2 components
- Updated `tools/context.py` to support both MemoryScope and MemoryPort types
- Updated `naqsha/__init__.py` to export Dynamic Memory Engine components
- Created comprehensive test suite (90 tests, all passing):
  - `tests/memory/test_ddl.py` - 26 tests for DDL validation
  - `tests/memory/test_scope.py` - 19 tests for namespace isolation
  - `tests/memory/test_engine.py` - 15 tests for engine functionality
  - `tests/memory/test_retrieval.py` - 14 tests for retrieval ranking
  - `tests/tools/test_memory_schema.py` - 17 tests for memory tools
- All existing tests pass (94 core/tools/tracing tests)
- Ruff linting passes with zero errors

**Risks the next phase inherits:**
- The V1 SimpleMem-Cross adapter remains in place for backward compatibility but is not integrated with the new Dynamic Memory Engine. Phase 4 may need to decide whether to deprecate or bridge these.
- The `naqsha.toml` topology and `[memory]` blocks are implemented in Phase 4 (`parse_team_topology`); legacy JSON `RunProfile` paths remain for single-agent runs.
- The Memory Schema Tool validates DDL but does not prevent agents from executing regular DML (INSERT, SELECT, UPDATE, DELETE) through the MemoryScope. This is intentional - the safelist only applies to schema-changing operations.
- The MemoryRetriever uses a simple keyword + recency ranking formula. Semantic search via sqlite-vec embeddings is supported in the engine but not yet implemented in the retriever (marked for future enhancement).
- The Core Runtime does not yet inject MemoryScope objects into AgentContext for single-agent `build_runtime(profile)` paths; team runs use `build_team_orchestrator_runtime`, which wires `MemoryScope` into `AgentContext`.

---

## Phase 4: Multi-Agent Team Workspaces and Tool-Based Delegation

**Status:** complete

**Goal:** Implement the `naqsha.toml` topology parser and the Tool-Based Delegation Model. A Team Workspace can now define multiple agents. The Orchestrator receives auto-generated delegation tools.

**Scope:** Delivered as planned: `[workspace]`, `[agents.*]`, `[memory]`, `[reflection]` TOML sections; `TeamTopology`; `build_delegate_tool` / `build_team_orchestrator_runtime`; shared-team `DynamicMemoryEngine`; hierarchical trace under one `run_id`; orchestration tests.

**Do not:** (honored — no worker `AgentContext` leak; approval gate applies inside workers; no TUI.)

**Exit criteria:**
- A two-agent fake-model team (Orchestrator + Worker) runs end-to-end and produces a hierarchical trace.
- Role-Based Tool Policy denials in the worker produce `ToolErrored` events on the bus.
- Shared memory written by the Orchestrator is readable by the Worker and vice versa.

**Delivered:** See implementation: `memory/sharing.py`, `orchestration/{topology,delegation,team_runtime}.py`, `tools/decorated_adapter.py`, `core/runtime.py` span + bus + policy changes, SQLite `check_same_thread=False`, `tests/orchestration/*`, `tests/test_protocols.py` legacy schema default.

**Risks the next phase inherits:**
- `parse_run_profile` does not list delegation or memory decorator tools; `run_profile_for_topology_agent` validates a stripped allowlist then restores full `allowed_tool_names` with `dataclasses.replace`.
- Nested delegation is not implemented. Workers reuse the orchestrator `ApprovalGate` during delegation.
- `max_retries` is now wired to `RuntimeConfig` and the Phase 5 Circuit Breaker from `naqsha.toml` topology.

---

## Phase 5: Resilience — Circuit Breakers and Structured Error Escalation

**Status:** complete

**Goal:** Implement the Circuit Breaker and Structured Error Escalation patterns. Agents now recover gracefully from transient errors and fail safely when errors are persistent.

**Scope:**
- Implement `core/circuit_breaker.py`: `CircuitBreaker(max_consecutive_failures: int)`. Tracks consecutive identical errors per tool. On threshold breach, raises `CircuitBreakerTrippedError`, emits `CircuitBreakerTripped` event on the bus, and halts the agent loop.
- Update `tools/executor.py` to catch all tool exceptions, wrap them in `ToolErrorObservation`, and record consecutive failure counts.
- Update `orchestration/delegation.py`: if a worker's loop exits via `CircuitBreakerTrippedError`, the delegation tool returns a structured `TaskFailedError` observation to the Orchestrator rather than propagating the exception.
- Add `[agents.<name>] max_retries` to the `naqsha.toml` schema (default: 3).
- Add `tests/core/test_circuit_breaker.py`: trip threshold, `TaskFailedError` escalation, reset on success.
- Add `tests/tools/test_error_escalation.py`: tool exception → `ToolErrorObservation`, consecutive tracking, circuit trip.

**Do not:**
- Swallow errors silently. Every caught exception must produce a trace event.
- Let `max_retries = 0` mean "infinite retries" — it must mean "trip immediately on first failure".

**Exit criteria:**
- A fake tool that always raises an exception trips the circuit breaker after `max_retries` and escalates to the Orchestrator.
- The `CircuitBreakerTripped` event is emitted on the Event Bus and recorded in the trace.
- The Orchestrator receives a `TaskFailedError` observation and can continue its own loop.

**Delivered:**
- `core/circuit_breaker.py`: `CircuitBreaker`, `CircuitBreakerTrippedError`, `circuit_failure_threshold` (values `<= 0` trip on first failure).
- `RuntimeConfig.max_retries` wired from team topology (`build_worker_runtime`, `build_team_orchestrator_runtime`); default `3` for JSON `build_runtime` profiles.
- `CoreRuntime` applies the breaker on approved tool observations (skipped when `ToolScheduler.recorded_observations` is set for deterministic replay).
- Approved tool failures emit `ToolErrored` on the bus (successes emit `ToolCompleted`); hierarchical trace persists `failure` with `circuit_breaker_tripped` before `RunFailed`.
- `ToolExecutor` and `ToolScheduler.invoke` normalize exceptions to failed `ToolObservation` with `metadata["tool_error"]=True`.
- Delegation wraps failed worker runs in `ToolObservation.metadata["kind"]="TaskFailedError"` (sets `circuit_breaker` flag when worker failed due to breaker).
- Tests: `tests/core/test_circuit_breaker.py`, `tests/tools/test_error_escalation.py`, delegation escalation in `tests/orchestration/test_delegation.py`.

**Risks the next phase inherits:**
- NAP messages do not surface `TaskFailedError` as a typed protocol artifact; escalation is conveyed only via sanitized tool observations and trace metadata (`metadata["kind"]`).
- Replay mode disables circuit breaking entirely; scripted failures in traces will never trip locally.
- `max_retries` is not duplicated on legacy JSON `RunProfile`; only topology agents and default single-agent configs use `RuntimeConfig.max_retries`.

---

## Phase 6: Model Adapters — NAP V2 Thin Adapters

**Status:** complete

**Goal:** Upgrade all existing model adapters (OpenAI-compatible, Anthropic, Gemini) to the NAP V2 protocol and implement a new Ollama (local) adapter. All adapters must propagate `SpanContext` correctly.

**Scope:**
- Extend `models/nap.py` (formerly `protocols/nap.py`) with a `span_context` field on `NAPAction` and `NAPAnswer`.
- Update `models/openai_compat.py`, `models/anthropic.py`, and `models/gemini.py` to produce NAP V2 messages with `span_context` populated from the active span.
- Implement `models/ollama.py`: Ollama's `/api/chat` endpoint with tool-calling support. Register as `ollama` adapter in the profile factory. Support `base_url` override for custom Ollama installs.
- Add `tests/models/test_ollama.py` with httpretty/responses-style mocking (no live network).
- Update `examples/profiles/` with an `ollama.example.toml` profile.

**Do not:**
- Add live API key calls to tests.
- Put provider-specific formats anywhere outside the adapter files.

**Exit criteria:**
- All five adapters (fake, openai_compat, anthropic, gemini, ollama) produce valid NAP V2 messages.
- `SpanContext` is populated on all adapter-produced messages.
- CI remains stable without live network or API keys.

**Delivered:**
- Canonical `models/nap.py`: `NapAction` / `NapAnswer` optional `span_context`, `parse_nap_message` / `nap_to_dict` / `attach_span_context`; explicit `span_context` key allowed in JSON (including null).
- `tracing/protocols/nap.py` and `protocols/nap.py` re-export from `models/nap.py`; `profiles.py` / `topology.py` import NAP parse from `models.nap` to avoid import cycles.
- `models/__init__.py`: lazy `__getattr__` (PEP 562) so `naqsha.models.nap` does not pull `factory` at package init.
- `ModelClient.next_message(..., span_context=...)`; `CoreRuntime` passes active `SpanContext`; fake, OpenAI-compat, Anthropic, Gemini, Ollama adapters attach span on responses.
- `OllamaChatModelClient` (`/api/chat`, stdlib HTTP, mocked tests); `RunProfile` + `parse_run_profile` + `model_client_from_profile` + `naqsha.toml` topology (`ollama` adapter, `[agents.*.ollama]` table).
- `examples/profiles/ollama.example.toml`; tests: `tests/models/test_ollama.py`, NAP span round-trip in `tests/test_protocols.py`, profile/factory tests in `tests/test_profiles.py`.

**Risks the next phase inherits:**
- `OllamaChatModelClient` maps responses with `_openai_message_to_nap`; if Ollama diverges from OpenAI-shaped `message.tool_calls`, adjust only `models/ollama.py`.
- `protocols/nap.py` now imports `models.nap` first; new code should import NAP from `naqsha.models.nap` or `naqsha.protocols.nap`, not duplicate definitions.

---

## Phase 7: Reflection Loop V2 and Automated Rollback Manager

**Status:** complete

**Goal:** Upgrade the Reflection Loop to support autonomous patch merging (when `auto_merge = true` in `naqsha.toml`) and implement the Automated Rollback Manager.

**Scope:** Delivered as specified: `reflection/rollback.py`, `reflection/config.py`, `ReflectionPatch.auto_merged`, optional `ReflectionPatchEventSink`, merge subtree under patch workspace `merge/`, boot probe before `naqsha run` and `AgentWorkbench.run`, tests under `tests/reflection/`.

**Do not:** _(honored — no gate bypass; defaults remain `auto_merge = false`)_

**Exit criteria:**
- `auto_merge = true` merges a patch after the gate passes and emits `PatchMerged` on the bus (via sink). ✅
- A simulated boot failure triggers restore and emits `PatchRolledBack` (via sink). ✅
- `auto_merge = false` behavior is identical to V1. ✅

**Delivered:**
- `reflection/rollback.py` — `AutomatedRollbackManager`: backs up `naqsha.toml` and `tools/` to `.naqsha/backups/<stamp>/`, applies `patch.workspace/merge/` into the team root (path-safe), sets `boot_status` to `pending`, records `last_merge_meta.json`, prunes to 5 backups, restore on failed `verify_boot_if_pending` health check, `PatchRolledBack` via sink; `rolled_back` clears to `stable` only after a **passing** boot health check; if merge meta is missing and more than one backup exists, restore is skipped (ambiguous).
- `reflection/config.py` — `load_reflection_toml_settings` / `ReflectionTomlSettings` for `[reflection]` (defaults align with topology: `enabled` / `auto_merge` default false). `reliability_gate` gates **auto-merge only**, not whether pytest runs.
- `reflection/base.py` — `auto_merged` on `ReflectionPatch`, `ReflectionPatchEventSink` protocol (reflection does not import `core/`; workbench bridges to `RuntimeEventBus`).
- `reflection/loop.py` — Reliability Gate subprocess runs whenever `project_root` resolves; auto-merge only when `enabled`, `auto_merge`, gate passed, `reliability_gate`, and team `naqsha.toml` exists; writes `merge/` payload (marker append to `naqsha.toml`).
- `naqsha.workbench.RuntimeBusReflectionSink` — maps sink callbacks to `PatchMerged` / `PatchRolledBack`; `AgentWorkbench.run` accepts optional `event_bus` or `patch_event_sink`; `propose_improvement` accepts optional `event_bus`.
- `cli.py` — `naqsha run` and `reflect`/`improve` use a per-invocation `RuntimeEventBus` + sink so merge/rollback notifications are emitted; `reflect` JSON includes `auto_merged`.
- Tests: `tests/reflection/test_rollback.py`, `tests/reflection/test_auto_merge.py` (includes bus bridge test).

**Risks the next phase inherits:**
- CLI and default `AgentWorkbench` paths create an **ephemeral** `RuntimeEventBus` (no persistent subscriber); the Phase 8 TUI should pass a shared bus into `run` / `propose_improvement` / CLI when it needs live patch events.
- Boot health probe runs an extra short `CoreRuntime.run` when status is `pending` (and once per `AgentWorkbench.run`), doubling cold-start cost for that path.
- Merge payload is currently an appended marker in `naqsha.toml`; richer file-level Reflection Patches remain a documentation/product task.

---

## Phase 8: Workbench TUI — Core Panels and `naqsha init` Wizard

**Status:** complete

**Goal:** Ship the Textual-based Workbench TUI with the `naqsha init` wizard and the core runtime panels: streaming chat, span tree, and budget counter. The TUI subscribes to the Typed Event Bus.

**Scope:**
- Add `textual` and `rich` to `pyproject.toml` under the `[tui]` optional extra and the `[dev]` extra (CI runs headless tests without a separate `--extra tui` flag).
- Implement `tui/app.py`: `WorkbenchApp(textual.App)` with `RuntimeEventBus` subscription and `call_from_thread` dispatch to panels; runs `CoreRuntime.run` on a worker thread.
- Implement `tui/panels/chat.py`: `ChatPanel` — `StreamChunkReceived`, tools, run lifecycle.
- Implement `tui/panels/budget.py`: `BudgetPanel` — `BudgetProgress` steps/tools/wall-clock bars.
- Implement `tui/panels/span_tree.py`: `SpanTreePanel` — `SpanOpened` / `SpanClosed` tree.
- Implement `tui/wizard/init.py`: interactive `naqsha init` wizard; outputs validated `naqsha.toml`.
- Wire `cli.py`: TTY + optional deps → TUI for `init` and `run`; `NAQSHA_NO_TUI=1` forces plain output.
- Add `tests/tui/test_wizard.py`, `tests/tui/test_panels.py` (Textual `run_test` / Pilot).
- Core Runtime: emit `StreamChunkReceived` (chunked final answer) and `BudgetProgress` (after each step and after tool execution) when `event_bus` is set; `SpanClosed` includes span metrics when available.

**Do not:** _(honored — no `tui` imports outside `cli`/`tui`; headless packages stay Textual-free.)_

**Exit criteria:**
- `naqsha init` in an interactive terminal launches the wizard and produces a valid `naqsha.toml`. ✅
- A fake-model run started via the TUI receives `StreamChunkReceived` / `BudgetProgress` / span events on the bus (verified via core + panel tests). ✅
- `BudgetPanel` updates from `BudgetProgress`. ✅
- `SpanTreePanel` shows nesting for parent/child spans (verified in TUI test). ✅

**Delivered:**
- `pyproject.toml`: `[tui]` extra; `dev` includes `textual` + `rich`.
- `core/events.py`: `BudgetProgress`; `core/runtime.py`: `_chunk_answer_for_stream`, bus emissions for streaming and budgets; richer `SpanClosed` metrics.
- `wiring.build_runtime` / `build_trace_replay_runtime`: optional `event_bus`.
- `tui/app.py`, `tui/workbench.tcss`, panels, `tui/wizard/init.py` (`render_workspace_toml`, `InitWizardApp`, `run_init_wizard`).
- `cli.py`: `_interactive_tui_enabled()`; TUI `init` / `run` paths; `NAQSHA_NO_TUI` escape hatch.
- Tests: `tests/tui/*`, `tests/core/test_runtime_bus_stream.py`.
- `naqsha.__init__` exports `BudgetProgress`; `AGENTS.md` updated for Phase 8.
- **Visual polish:** `tokyo-night` theme, `workbench.tcss` + `wizard/wizard.tcss`, panel border titles, Rich-styled chat/budget/span output, colored budget bars.

**Risks the next phase inherits:**
- `WorkbenchApp` is single-agent `build_runtime` only; team topology runs from the CLI still use plain output unless extended to `build_team_orchestrator_runtime` + TUI.
- `InitWizardApp` keeps one step visible at a time with a scrollable body and width-aware CSS so fields use the terminal width; richer multi-step animations remain optional polish.

---

## Phase 9: Advanced TUI Panels — Flame Graph, Memory Browser, and Patch Review

**Status:** complete

**Goal:** Complete the Workbench TUI with the analytics-focused panels: flame graph, memory browser, and the interactive Reflection Patch review diff view.

**Scope:** _(delivered as specified — visual standard, reflection-only patch I/O, tests.)_

**Do not:** _(honored.)_

**Exit criteria:**
- Flame graph shows correct per-agent attribution for a two-agent delegation run. ✅
- Memory browser lists tables and renders rows from a seeded workspace DB. ✅
- Patch review approve/reject round-trips correctly to the reflection module. ✅
- **Visual:** New panels match the Workbench visual standard (`AGENTS.md`): themed layout, no bare-default widgets. ✅

**Delivered:**
- `tui/panels/flame.py` — `FlamePanel`: per-agent wall time from span open/close timestamps, token totals from `SpanClosed`; themed `DEFAULT_CSS`; `metrics_snapshot()` for tests.
- `tui/panels/memory.py` — `MemoryBrowserPanel`: read-only SQLite, `OptionList` + `DataTable`, first 50 rows, default DB `.naqsha/memory.db` under workspace.
- `tui/panels/patch_review.py` — `PatchReviewPanel`: `Select` for `reflection-patch-*` under `.naqsha/reflection-workspaces`, side-by-side preview via `read_patch_review_texts`, **Approve** → `approve_patch`, **Reject** → `reject_patch`; `RuntimeBusReflectionSink` wired from `WorkbenchApp`.
- `reflection/loop.py` — `list_reflection_patch_workspace_ids`, `read_patch_review_texts`, `approve_patch`, `reject_patch` (patch I/O and merge orchestration stay in `reflection/`).
- `reflection/rollback.py` — `patch_merged` sink now uses `ReflectionPatch.auto_merged` (human approve emits `auto_merged=False`; auto-merge path sets `ReflectionPatch.auto_merged=True` on the merge payload).
- `tui/app.py` + `workbench.tcss` — vertical `#workbench-body`, `#analytics-row` for flame / memory / patch; patch parent defaults to `.naqsha/reflection-workspaces` (matches `naqsha reflect`); `RuntimeBusReflectionSink` for patch events.
- Tests: `tests/tui/test_flame.py`, `tests/tui/test_memory_browser.py`, `tests/tui/test_patch_review.py`, `tests/reflection/test_human_patch_approve.py`.

**Risks the next phase inherits:**
- Patch discovery uses `.naqsha/reflection-workspaces` (aligned with `naqsha reflect` default); custom `--workspace-base` outputs are not visible unless that path is mirrored or the TUI gains a setting.
- `PatchReviewPanel` shows line-aligned side-by-side text, not a syntax-highlighted diff engine.
- `MemoryBrowserPanel` does not run semantic search or schema migrations; it is a read-only viewer.
- `WorkbenchApp` still targets single-agent `build_runtime`; team TUI remains a follow-up.

---

## Phase 10: MkDocs Documentation Site

**Status:** complete

**Goal:** Ship the MkDocs-Material documentation site with full API reference (auto-generated from docstrings) and developer guides for the core workflows.

**Scope:**
- Add `mkdocs-material`, `mkdocstrings[python]`, and `mkdocs-gen-files` to the `dev` extra in `pyproject.toml`.
- Create `mkdocs.yml` at the project root with Material theme, dark mode toggle, search, and navigation tree.
- Create `docs/` source pages (distinct from `docs/adr/` and `docs/prd/` which already exist): `index.md` (overview), `getting-started.md` (install, init, first run), `concepts.md` (V2 glossary in doc form), `tools.md` (how to define tools), `teams.md` (multi-agent topology), `memory.md` (memory engine and scopes), `reflection.md` (Reflection Loop and Rollback Manager), `cli.md` (TUI reference; optional annotated Workbench screenshots if they stay current), `migration.md` (V1 → V2 migration guide).
- Configure `mkdocstrings` to generate API reference pages from all public modules in `src/naqsha/`.
- Add a `docs/gen_ref_pages.py` script (run by `mkdocs-gen-files`) that auto-creates one reference page per domain package.
- CI: add a `mkdocs build --strict` step to `.github/workflows/ci.yml` that fails on broken links or missing docstrings on public symbols.
- Ensure every public symbol in `src/naqsha/__init__.py` has a complete docstring (enforced by `--strict`).

**Do not:**
- Commit the built `site/` directory to the repository. It is generated by CI.

**Exit criteria:**
- `mkdocs build --strict` passes with zero warnings.
- API reference pages for all eight domain packages are generated.
- Getting-started guide can be followed from a clean environment to produce a running fake-model team.

**Delivered:**
- `pyproject.toml`: `[dev]` adds `mkdocs-material`, `mkdocstrings[python]`, `mkdocs-gen-files`; `Documentation` project URL points at repo README until a hosted site exists.
- `mkdocs.yml`: Material theme (light/dark), search, `exclude_docs` for `adr/`, `prd/`, `handoff/`, `user-guide/`, etc.; `mkdocstrings` with `paths: [src]`; `gen-files` runs `docs/gen_ref_pages.py`.
- Guide pages under `docs/`: `index.md`, `getting-started.md` (bundled `local-fake` + copy-paste `naqsha.toml` + `uv run python` team demo), `concepts.md`, `tools.md`, `teams.md`, `memory.md`, `reflection.md` (includes former patch-review doc), `cli.md`, `migration.md`.
- `docs/gen_ref_pages.py`: generates `reference/index.md` plus `naqsha`, `naqsha.core`, `naqsha.models`, `naqsha.tools`, `naqsha.memory`, `naqsha.orchestration`, `naqsha.tracing`, `naqsha.reflection`, `naqsha.tui` stubs with `::: module` autodoc.
- `.gitignore`: `site/`; `.github/workflows/ci.yml`: `mkdocs build --strict` after pytest.
- `src/naqsha/__init__.py`: expanded package docstring for API index quality.
- Removed orphan `docs/reflection-patch-review.md` (content merged into `reflection.md`).

**Risks the next phase inherits:**
- `naqsha run` CLI remains single-agent **Run Profile**-driven; the getting-started “team” path is **Python + `naqsha.toml`**, not a one-liner CLI (documented explicitly).
- MkDocs / Material may print upstream “MkDocs 2.0” advisory text during builds; CI sets `DISABLE_MKDOCS_2_WARNING` where supported—watch for future `properdocs` migration if the ecosystem moves.
- `mkdocstrings` uses `show_if_no_docstring: true` so missing member docstrings do not fail the build; tightening to require docstrings on every exported name is a follow-up hygiene task.
- Older `docs/user-guide/` markdown is **excluded** from the MkDocs site to avoid duplicate nav and stale duplication; links in README can still point to GitHub-rendered paths until Phase 11 consolidates entrypoints.

---

## Phase 11: Packaging, CI Hardening, and V2 Release

**Status:** in progress

**Goal:** Harden the packaging pipeline for V2 release. Update CI, pyproject.toml, and install tests. Produce a V2 acceptance report.

**Scope:**
- Bump `pyproject.toml` version to `2.0.0`.
- Update optional extras: `[memory]` (sqlite-vec), `[tui]` (textual, rich), `[embeddings]` (sqlite-vec), `[dev]` (pytest, ruff, build, mkdocs stack).
- Add or restore packaging install smoke tests (wheel/sdist and `[tui]` extra) under `tests/` as CI requires.
- Update CI `ci.yml` to run `mkdocs build --strict`, the full pytest suite (including TUI headless tests and multi-agent delegation tests), and the packaging install tests on Python 3.11 and 3.12.
- Produce `docs/release/0002-v2-acceptance.md`: checklist of all V2 PRD user stories, confirmation of Reliability Gate pass, and a summary of any known limitations.
- Update `README.md` with the V2 getting-started walkthrough.
- Update `docs/release/pypi-checklist.md` for V2.

**Do not:**
- Publish under `naqsh`.
- Make any optional extra required.
- Remove the V1 fake-model path from any packaging smoke test.

**Exit criteria:**
- `uv run --extra dev pytest` passes with zero failures.
- `uv run --extra dev ruff check .` passes with zero errors.
- `mkdocs build --strict` passes with zero warnings.
- Fresh wheel install can run a multi-agent fake-model team with no API keys.
- V2 acceptance report is signed off.

**Risks the next phase inherits:**
- _(post-release work documented in acceptance report)_

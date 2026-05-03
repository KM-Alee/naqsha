# NAQSHA V2 Runtime PRD

## Problem Statement

Developers building AI agent applications today face a painful set of trade-offs. Lightweight frameworks (or hand-rolled ReAct loops) break under the weight of production concerns: they lack durable memory, reproducible traces, enforced safety policies, and any mechanism for the agent to evolve over time. Meanwhile, heavy frameworks (LangGraph, AutoGen, CrewAI) solve some of these problems but introduce steep learning curves, verbose class hierarchies, complex graph-routing engines, and opaque internals that are extremely difficult to debug when something goes wrong.

NAQSHA V1 was a step in the right direction: it provided an inspectable ReAct runtime with QAOA Tracing, Tool Policy enforcement, Approval Gates, and durable memory. But V1 has significant limitations that prevent it from being used as a serious agent application development platform:

1. **Verbose, class-heavy developer API.** Defining a new tool requires inheriting from base classes, manually declaring JSON schemas, and implementing specific lifecycle methods. This creates an enormous amount of boilerplate and makes the tool definitions difficult to read and maintain. Developers want the elegance of a FastAPI endpoint, not a Django class-based view.

2. **Single-agent paradigm.** V1 has no concept of agent teams, orchestrators, or workers. Building a pipeline that involves multiple specialized agents (e.g., a Planner, a Coder, and a QA agent) requires wiring them together manually outside the framework, which defeats the point of having a runtime.

3. **Static, schema-locked memory.** V1's SimpleMem-Cross adapter uses a fixed session-based memory schema. An autonomous agent that discovers it needs to store new categories of information (e.g., user preferences, code snippets, task history) cannot restructure its own memory. It is stuck in the structure it was born with.

4. **No visual developer interface.** The V1 CLI is a simple text parser. There is no way to visually track what an agent is doing, see token consumption, cost estimates, or understand why a multi-step run went wrong. Debugging requires manually reading raw JSONL files.

5. **No framework for agent autonomy.** V1's Reflection Loop generates patches but requires mandatory human review with no automation pathway. This is appropriate as a default but prevents agents from being deployed in contexts where supervised autonomy is acceptable and desired.

6. **Flat, single-agent QAOA Traces.** A flat trace format is sufficient for a single agent but becomes an unreadable mess when multiple agents are delegating to each other, spawning sub-tasks, and merging results. There is no way to understand which agent spent how many tokens, or trace a delegation chain visually.

7. **Tightly coupled CLI and Core Runtime.** V1's core runtime outputs text and interacts with the CLI. This prevents it from being embedded cleanly in web backends, background workers, or other non-terminal environments.

## Solution

NAQSHA V2 is a comprehensive architectural overhaul that solves all of the above problems while maintaining the safety-first, inspectable, production-shaped principles of V1. It introduces seven major changes:

1. **Decorator-Driven API with Context-Aware Dependency Injection.** Tools are defined as ordinary Python functions with an `@agent.tool` decorator. The framework generates schemas from type hints and docstrings automatically. Accessing runtime state (memory, spans, config) is done through a clean `ctx: AgentContext` parameter rather than global state.

2. **Team Workspaces with Multi-Agent Orchestration.** The fundamental unit of deployment shifts from a single agent to a Team Workspace: a self-contained folder with a `naqsha.toml` topology file that defines multiple specialized agents, their models, their tools, and their Role-Based Tool Policies. Orchestration is implemented via a Tool-Based Delegation Model — the Orchestrator simply calls a `delegate_to_worker(task)` tool, keeping the core runtime simple and loop-based rather than requiring a complex graph engine.

3. **Dynamic Memory Engine.** SQLite-backed memory allows agents to autonomously evolve their own schema (via DDL), with both Shared Memory (team-wide collaboration) and Private Memory (agent-specific scratchpads). Vector embeddings via `sqlite-vec` are an opt-in workspace configuration flag.

4. **Workbench TUI.** A beautiful, reactive Terminal User Interface (built with Textual and Rich) that provides interactive configuration wizards, live streaming text, token/cost counters, and flame-graph views of multi-agent execution trees powered by the Hierarchical QAOA Trace.

5. **Typed Event Bus.** The Core Runtime becomes a headless library that emits strongly-typed Pydantic events. The TUI, background workers, and any future adapters subscribe to this event stream. The core never knows or cares what is listening.

6. **Hierarchical QAOA Trace.** Every trace event carries `span_id`, `parent_span_id`, and `agent_id`, enabling OpenTelemetry-style attribution of time and tokens across complex multi-agent execution trees.

7. **Supervised Autonomy with Automated Rollback.** Agents can be given permission to autonomously merge Reflection Patches. An Automated Rollback Manager saves a snapshot before every merge and reverts the workspace if the subsequent boot fails or is immediately catastrophically broken.

## User Stories

### Developer Experience

1. As a Python developer, I want to define tools using ordinary Python functions decorated with `@agent.tool`, so that I can write tool definitions as naturally as I write any other function.
2. As a Python developer, I want the framework to automatically derive strict JSON schemas from my function's type hints and docstrings, so that I get strong input validation without writing any schema boilerplate.
3. As a Python developer, I want to use standard Pydantic models as tool parameters, so that complex nested input types are validated and documented automatically.
4. As a Python developer, I want to write `async def` tool functions, so that I can perform non-blocking network I/O in tools without blocking the event loop.
5. As a Python developer, I want to inject runtime context into my tools via a `ctx: AgentContext` type hint, so that I can access shared memory, private memory, and run metadata without using global variables.
6. As a Python developer, I want to receive a clear, human-readable error at import time if my tool function's signature is malformed, so that mistakes are caught early rather than at runtime.
7. As a library consumer, I want to import `naqsha` and get access to the entire public API from a single flat namespace (e.g., `from naqsha import agent, AgentContext, tool`), so that I don't need to know the internal package structure.
8. As a library consumer, I want the Core Runtime to be a pure headless library, so that I can embed it in a FastAPI backend, a Celery worker, or any other non-terminal Python environment.
9. As a library consumer, I want to subscribe to the Typed Event Bus and receive strongly-typed Pydantic events, so that I can build custom UIs, loggers, or monitoring integrations on top of the runtime.

### Team Workspaces and Orchestration

10. As an agent developer, I want to run `naqsha init` and be guided through a pretty interactive wizard that asks me for the team name, agents, models, memory type, and tool selection, so that I can bootstrap a Team Workspace without reading documentation first.
11. As an agent developer, I want to define a Team Workspace in a `naqsha.toml` file that specifies multiple agents, their models, their roles, and their tool policies, so that my team configuration is explicit, versioned, and reproducible.
12. As an agent developer, I want the Orchestrator to delegate to workers simply by calling an auto-generated `delegate_to_<worker_name>(task: str)` tool, so that multi-agent coordination feels as natural as tool use.
13. As an agent developer, I want delegated sub-agents to complete their full execution loop (including tool use and memory reads) before returning their final answer to the Orchestrator as a tool observation, so that I don't have to manage complex state synchronization.
14. As an agent developer, I want each worker agent in a team to have its own Role-Based Tool Policy, so that a Coder agent can write files but a QA agent can only read them and run tests.
15. As an agent developer, I want to assign different models to different agents in the team topology (e.g., Claude 3.5 Sonnet for the Orchestrator, a fast local model for a formatter), so that I can optimize the team for cost and capability.
16. As an agent developer, I want the framework to ship with Thin Adapters for OpenAI-compatible APIs, Anthropic, and Ollama out of the box, so that I can connect to cloud and local models with minimal configuration.
17. As an agent developer, I want to write a custom Model Adapter in a single Python class by implementing a simple interface, so that I can connect to new or private models without waiting for an official adapter.

### Dynamic Memory Engine

18. As an agent developer, I want my agent's memory to be persisted to a local SQLite database within the Team Workspace, so that memory survives process restarts without any external infrastructure.
19. As an agent developer, I want to configure whether my Team Workspace uses vector embeddings for semantic search via a single line in `naqsha.toml`, so that I can get semantic recall without managing a separate vector database.
20. As an agent (runtime perspective), I want access to a Memory Schema Tool in my tool set, so that I can autonomously create new tables or columns in my own database as my tasks evolve.
21. As an agent developer, I want agents within the same team to be able to read and write to a Shared Memory namespace, so that they can collaborate on structured data without injecting it into context windows.
22. As an agent developer, I want each agent to have a Private Memory namespace that other agents cannot read, so that agents can maintain internal scratchpads and intermediate working state without polluting the shared context.
23. As an agent developer, I want all memory writes to be wrapped in SQLite transactions, so that a tool failure midway through a complex memory update never leaves the database in an inconsistent state.
24. As a developer, I want memory retrievals to be token-budgeted and provenance-annotated, so that useful memories compete explicitly with tool schemas rather than silently overflowing the context window.

### Workbench TUI and CLI

25. As a CLI user, I want to launch an interactive `naqsha init` wizard from the terminal, so that I can configure a Team Workspace visually without memorizing a configuration schema.
26. As a CLI user, I want the TUI to stream agent output live (token by token) in a dedicated panel, so that I can watch my agent's reasoning as it happens rather than waiting for a final answer.
27. As a CLI user, I want to see a live token counter, cost estimate, and budget utilization bar in the TUI, so that I always know how much of my budget is remaining during a run.
28. As a CLI user, I want to pause and inspect a running agent from within the TUI, so that I can review its progress on a long-running task before it completes.
29. As a CLI user, I want to view the QAOA Trace as an interactive expandable tree in the TUI, where each agent has its own collapsible section showing its spans, so that I can navigate complex multi-agent runs easily.
30. As a CLI user, I want to see a flame-graph view of time and token consumption across agents in the TUI, so that I can immediately identify which agent is the bottleneck.
31. As a CLI user, I want to manage, list, delete, and inspect my Team Workspaces from the TUI, so that I can administer all my agents from a single interface.
32. As a CLI user, I want to review and approve a pending Reflection Patch from within the TUI (with a diff view), so that the approval workflow is streamlined and visual.

### Resilience, Autonomy and Error Handling

33. As a framework user, I want tool exceptions to be automatically caught, wrapped in a structured `ToolErrorObservation`, and returned to the agent, so that transient errors give the agent a chance to self-correct without crashing the process.
34. As a framework user, I want a Circuit Breaker that halts a worker agent if it hits the same error more than a configurable number of consecutive times, so that I am protected from infinite loops consuming API budget.
35. As an Orchestrator agent, I want to receive a `TaskFailedError` structured observation if a delegated worker trips its Circuit Breaker, so that I can decide to reroute the task, try an alternative strategy, or report the failure.
36. As an agent developer, I want a workspace-level `max_retries` setting in `naqsha.toml` that configures the Circuit Breaker threshold, so that I can tune the resilience behavior without changing code.
37. As an autonomous agent, I want to be able to generate a Reflection Patch and, if my workspace is configured with `auto_merge = true`, have it automatically applied after the Reliability Gate passes, so that I can continuously improve without requiring human intervention in supervised deployments.
38. As a developer deploying an autonomous agent, I want the Automated Rollback Manager to save a snapshot of the workspace before every autonomous patch merge, so that a bad code change is automatically reverted if the subsequent boot fails.
39. As a developer, I want the Automated Rollback Manager to maintain a history of the last 5 stable workspace states, so that I can manually roll back if an agent's performance degrades subtly without explicitly crashing.
40. As a security-conscious developer, I want `auto_merge = true` to be an explicit opt-in that defaults to `false` in all workspace templates and the init wizard, so that agents never gain autonomous code modification by accident.

### Tracing and Observability

41. As an agent developer, I want every QAOA Trace event to carry a `span_id`, `parent_span_id`, and `agent_id`, so that the complete execution tree of a multi-agent run is reconstructable from the trace file.
42. As a developer debugging a regression, I want to replay a Hierarchical QAOA Trace from a previous run, so that I can reproduce a complex multi-agent interaction deterministically without re-running all agents live.
43. As a developer, I want the trace file to record token counts, model latency, and tool execution time at the span level, so that performance profiling is data-driven rather than guess-based.
44. As a developer, I want the Observation Sanitizer to continue running on all tool outputs before they enter any trace, memory write, or model context, so that secret-like strings are never persisted or injected.

### Documentation and Packaging

45. As a developer exploring the framework, I want to find beautiful, comprehensive documentation at a single MkDocs-Material site, so that I can learn by reading rather than by reading source code.
46. As a developer, I want API reference documentation to be automatically generated from the Python docstrings in the source code, so that the docs are always accurate and never stale.
47. As a contributor, I want the project structured according to the Domain-Driven `src/` layout convention, so that module boundaries are physically enforced by the filesystem.
48. As a package maintainer, I want the `naqsha` PyPI distribution to cleanly separate its optional extras (`[tui]`, `[embeddings]`, `[dev]`), so that lightweight server-side embeddings are not forced on CLI users and vice versa.

## Implementation Decisions

### 1. Domain-Driven `src/` Layout
The codebase will be migrated from the V1 flat-ish structure to a strict domain-based package hierarchy inside `src/naqsha/`. Every domain package owns its public interface and is responsible for preventing its internal details from leaking outward. The dependency graph between packages must be a strict DAG (no cycles), enforced in CI via `ruff` import rules if needed.

```
src/naqsha/
├── __init__.py          # flat public API: agent, tool, AgentContext, etc.
├── core/                # headless engine: Event Bus, runtime loop, budget enforcement
├── models/              # NAP V2 protocol + Thin Adapters (openai, anthropic, ollama, fake)
├── tools/               # @agent.tool decorator, dependency injection, schema generation
├── memory/              # Dynamic Memory Engine: SQLite, sqlite-vec, scope management
├── orchestration/       # naqsha.toml topology parser, Tool-Based Delegation logic
├── tracing/             # Hierarchical QAOA Trace models, span management, sanitizer
├── reflection/          # Reflection Loop, Automated Rollback Manager, patch I/O
└── tui/                 # Textual TUI application, all panels, wizards, dashboards
```

### 2. Typed Event Bus
The `core.event_bus` module will define a `RuntimeEventBus` class with a subscription model. All events will be Pydantic `BaseModel` subclasses under the `core.events` namespace. Key events include: `RunStarted`, `AgentActivated`, `StreamChunkReceived`, `ToolInvoked`, `ToolCompleted`, `ToolErrored`, `SpanOpened`, `SpanClosed`, `CircuitBreakerTripped`, `PatchMerged`, `PatchRolledBack`, `RunCompleted`, `RunFailed`. The `tui` package subscribes to this bus. The `core` package must not import from the `tui` package under any circumstances (enforced by import linting).

### 3. Decorator-Driven API and Dependency Injection
The `tools.decorator` module implements `@agent.tool`. On decoration, it uses `inspect.signature` and `typing.get_type_hints` to build a JSON Schema Draft 2020-12 definition, stored on the function as `__tool_schema__`. At execution time, the `tools.executor` module checks for `AgentContext`-typed parameters and injects the live context via keyword arguments. The `AgentContext` object will expose: `shared_memory`, `private_memory`, `span`, `workspace_path`, `agent_id`, and `run_id`. The public surface for tool authors is intentionally minimal.

### 4. Hierarchical QAOA Trace Schema
The V2 trace schema will be a strict superset of V1. Every event carries: `schema_version` (bumped to `2`), `trace_id`, `span_id`, `parent_span_id` (null for root), `agent_id`, `timestamp_utc`, `event_type` (`query`, `action`, `observation`, `answer`, `error`), and `payload`. Delegation opens a new child span automatically. Token counts, model latency, and tool execution time are recorded as first-class span attributes, not optional payload fields.

### 5. Tool-Based Delegation Model
The `orchestration.topology` module reads `naqsha.toml` and, for each worker agent defined, calls `orchestration.delegation.build_delegate_tool(worker_config)` which returns a function registered as a standard tool. This function, when invoked by the orchestrator, creates a new child span, instantiates the worker's Core Runtime with its own config, and `await`s the worker's final answer. The orchestrator's `AgentContext` is never passed to the worker (strict isolation). The worker's full Hierarchical QAOA Trace is emitted as child spans under the delegation span.

### 6. Dynamic Memory Engine
The `memory.engine` module wraps SQLite via the standard `sqlite3` library. The `memory.scope` module enforces namespace isolation: Shared Memory uses a `shared_` table prefix, Private Memory uses a `private_<agent_id>_` prefix, enforced at the SQL level with schema constraints. If `embeddings = true` in `naqsha.toml`, the engine loads `sqlite-vec` via the `[embeddings]` optional extra and creates vector tables automatically. DDL executed via the Memory Schema Tool is wrapped in transactions and subject to a DDL safelist (only `CREATE TABLE`, `CREATE INDEX`, `ALTER TABLE ADD COLUMN` are permitted) to prevent destructive schema operations.

### 7. Automated Rollback Manager
The `reflection.rollback` module implements the full snapshot/restore lifecycle. Before any Reflection Patch merge, it copies the affected files (custom tools directory, `naqsha.toml`) to `.naqsha/backups/<iso-timestamp>/`. On the next runtime boot, the manager checks a `.naqsha/boot_status` file. If it reads `pending`, the manager runs a health check. If the health check fails, it restores the most recent backup and writes `rolled_back` to `boot_status`. If it succeeds, it writes `stable`. The five most recent backups are retained; older ones are pruned.

### 8. Workbench TUI Architecture
The `tui` package is a standalone `textual.App` subclass. It constructs the Core Runtime headlessly, subscribes to the `RuntimeEventBus`, and maps events to Textual reactive state updates. All TUI layout is defined in Textual CSS (`.tcss` files in `tui/styles/`). Panels include: `ChatPanel` (streaming text), `SpanTreePanel` (expandable QAOA Trace tree), `FlamePanel` (time/token bar chart), `BudgetPanel` (counters), `MemoryBrowserPanel` (SQLite table viewer), `PatchReviewPanel` (diff viewer for Reflection Patches). The `tui` package has its own optional extra (`[tui]`) in `pyproject.toml` so users embedding the headless library do not need to install Textual.

### 9. `naqsha.toml` Schema
The workspace configuration file will use TOML. The top-level keys are: `[workspace]` (name, description, base_model, memory settings), `[agents.<name>]` (one section per agent: role, model_adapter, tools, max_steps, max_tokens, max_retries), `[memory]` (type: `sqlite`, embeddings: bool, db_path), `[reflection]` (enabled: bool, auto_merge: bool, reliability_gate: bool). The profiles parser will be extended to load this new schema in addition to the V1 JSON Run Profile format.

### 10. NAP V2 Protocol
The existing NAP protocol will be extended with a `span_context` field carrying the `trace_id`, `span_id`, and `agent_id` that the Model Adapter should propagate. The NAP V2 schema version will be bumped. V1 NAP messages (without `span_context`) will continue to be parsed by the V2 runtime as version-1 messages for backward compatibility with existing traces. The `protocols/nap.py` module will own this evolution, and `SUPPORTED_SCHEMA_VERSIONS` must be updated.

## Testing Decisions

- **Philosophy**: Tests must exercise externally observable behavior only. Good test targets: emitted events on the bus, generated JSON schemas, database state after memory operations, trace file contents, CLI output, and patch manager file system state. Bad test targets: private method call order, internal dataclass field names, exact prompt strings (unless they are part of a public contract), and import paths.

- **Core Event Bus**: A fake subscriber must be able to register with the Event Bus and collect all emitted events in order. Tests verify that a standard single-agent run emits the correct event sequence: `RunStarted`, `AgentActivated`, `ToolInvoked`, `ToolCompleted`, `SpanClosed`, `RunCompleted`. Tests verify that delegation emits a correctly nested child span with the expected `parent_span_id`.

- **Decorator and Injection**: Test that `@agent.tool` generates a valid JSON Schema Draft 2020-12 from a function with primitive types, a Pydantic model parameter, a default argument, and an `Optional` type. Test that `AgentContext` is injected when requested and cleanly omitted from the generated schema. Test that a malformed signature raises a clear `ToolDefinitionError` at decoration time.

- **Dynamic Memory**: Test that Shared Memory and Private Memory writes go to different namespaced tables. Test that an agent cannot read another agent's private memory via `AgentContext`. Test that DDL executed via the Memory Schema Tool with a forbidden operation (e.g., `DROP TABLE`) raises an error and does not execute. Test transactional rollback by simulating a failure mid-write.

- **Orchestration and Delegation**: Test that a Team Workspace with two agents generates a delegation tool visible in the orchestrator's tool policy. Test that invoking the delegation tool runs the worker's runtime loop and returns the correct final answer. Test that the worker's trace events appear as child spans of the delegation span.

- **Circuit Breakers**: Test that a tool raising the same exception consecutively trips the circuit breaker after the configured threshold. Test that the orchestrator receives a `TaskFailedError` observation. Test that `max_retries = 1` trips on the first failure.

- **Automated Rollback**: Test that a Reflection Patch merge creates a backup directory with the correct files. Simulate a boot failure (by writing `pending` to `boot_status`) and verify the rollback restores the backup files and writes `rolled_back`. Test that the 5-backup rotation prunes old snapshots.

- **TUI**: Use Textual's `Pilot` testing API to simulate a user launching `naqsha init`, navigating the wizard, and verifying the generated `naqsha.toml`. Use `Pilot` to test that a streaming run emits tokens into the `ChatPanel` and that the `BudgetPanel` updates.

- **V1 Backward Compatibility**: Verify that a valid V1 QAOA Trace JSONL file can be loaded and replayed by the V2 tracing module without error.

- **Test Layout**: All tests live in `tests/`, mirroring the domain packages in `src/naqsha/`. The red-team corpus in `tests/redteam/` is expanded to cover multi-agent delegation injection attacks (e.g., a worker returning content that attempts to issue instructions to the orchestrator through its observation).

## Out of Scope

- Backward API compatibility with V1 class-based tool definitions. V2 is a major version with breaking changes. Migration guidance will be provided in documentation.
- Complex graph-based routing engines (LangGraph, AutoGen-style state machines). The Tool-Based Delegation Model covers the required orchestration without this complexity.
- Hosted cloud services, multi-tenant platforms, remote telemetry collection, or any SaaS component.
- Integration with third-party model-translation libraries such as `litellm`. NAP V2 Thin Adapters are the only model integration path.
- Multimodal inputs or outputs (images, audio) in V2. Text-only for the initial V2 release.
- A web-based (browser) UI. The Workbench TUI is terminal-only in V2.
- Automatic migration of V1 Team Workspace (`.naqsha/`) directories to the new format. Users must re-initialize workspaces using the new wizard.

## Further Notes

### V1 to V2 Migration Path
V1 continues to function as published on PyPI. V2 will be released as `naqsha>=2.0.0` and will explicitly require `python>=3.11`. A migration guide will be maintained in `docs/migration/v1-to-v2.md`.

### V2 Development Phases
See `docs/handoff/0002-v2-development-workflow.md` for the full phased execution plan, phase-by-phase acceptance criteria, and instructions for agent-driven development sessions. This handoff document is the source of truth for current phase status and must be updated by the completing agent at the end of every phase.

### Safety Guarantees That Must Be Preserved From V1
Even in V2, the following constraints must be maintained:
- All tool output is an Untrusted Observation and must never be treated as a runtime instruction.
- The Observation Sanitizer runs before any trace write, memory write, or model context injection.
- Budget Limits fail closed. Exhausted budgets are not warnings.
- `auto_merge = false` is always the default in wizard-generated workspaces.
- The `tui` package must never be imported by `core`, `models`, `tools`, `memory`, `orchestration`, `tracing`, or `reflection`.

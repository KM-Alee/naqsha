# Concepts

NAQSHA V2 uses precise vocabulary across code, documentation, and Architecture Decision Records. This page is the developer's reference; the full glossary lives in [CONTEXT.md](https://github.com/KM-Alee/naqsha/blob/main/CONTEXT.md).

---

## Runtime and workspace

### NAQSHA

The Python library and CLI (`naqsha`). Not a hosted platform, not a cloud service — a local library you install and embed.

### Core Runtime

The **headless** execution engine. It runs the agent loop, dispatches tool calls, enforces Tool Policy, emits Typed Events, tracks budgets, and writes traces. It must never import from `tui/`.

### Team Workspace

A directory whose root contains `naqsha.toml`. It holds:

- Agent topology and Run Profiles
- Shared and private memory (SQLite)
- QAOA Trace files (`.naqsha/traces/`)
- Reflection Patch workspaces (`.naqsha/reflection-workspaces/`)
- Workspace backups (`.naqsha/backups/`)

### Agent Workbench

The CLI and library workflows wrapping the Core Runtime: initialise a workspace, run queries, inspect QAOA Traces, replay and evaluate runs, and propose Reflection Patches for review.

### Run Profile

A named configuration that selects the model adapter, tool allowlist, budget caps, memory settings, trace location, and approval behaviour. Stored as JSON (single-agent) or in `naqsha.toml` (multi-agent).

---

## Safety model

### NAP Action

The strict model-facing action envelope. The Core Runtime only speaks **NAP V2** internally. Every model interaction is serialised through a thin adapter; provider-specific formats never appear outside adapter files.

NAP V2 fields:

| Field | Type | Description |
|---|---|---|
| `kind` | `"action"` or `"answer"` | Action type |
| `calls` | `list[ToolCall]` | Tool calls requested by the model |
| `text` | `str \| None` | Final answer (when `kind = "answer"`) |
| `span_context` | `SpanContext \| None` | Active span for hierarchical tracing |

### Untrusted Observation

All tool output. It may **inform** the model but must **never instruct the runtime**. Tool observations are data, not commands.

### Observation Sanitizer

Runs before **every** trace write, memory write, and model context injection. Redacts secret-like patterns and policy-forbidden content. No raw tool output ever bypasses it.

### Tool Policy

Runtime rules deciding which tools a run may call. Expressed as an allowlist per agent in `naqsha.toml`. Denials emit `ToolErrored` on the Event Bus and are recorded in the trace.

### Role-Based Tool Policy

In multi-agent teams, each agent has its own tool allowlist. An agent cannot call a tool that is not in its allowlist — even if the tool is registered in the global registry.

### Approval Gate

A Tool Policy checkpoint that requires explicit human (or callback) approval before a `write`-tier or `side-effect`-tier tool executes. Two implementations:

- **`StaticApprovalGate`** — always approves or always denies (for tests and `auto_approve = true`).
- **`InteractiveApprovalGate`** — blocks execution and prompts the user in the terminal.

### Budget Limit

A hard cap on: steps, tokens, tool calls, per-tool wall-clock time, and total wall-clock time. All fail **closed** — exhausted budgets produce structured `RunFailed` events, not warnings.

### Circuit Breaker

Tracks consecutive identical tool failures per tool name. On threshold breach:

1. Raises `CircuitBreakerTrippedError` inside the agent loop.
2. Emits `CircuitBreakerTripped` on the Event Bus.
3. Writes `circuit_breaker_tripped` to the trace.
4. Delegation wraps the failure as a `TaskFailedError` observation returned to the orchestrator.

Disabled during trace replay (recorded observations never cause fresh trips).

---

## Tracing

### QAOA Trace

**Q**uery → **A**ction → **O**bservation → **A**nswer. The canonical record of an agent run. Stored as append-only JSONL. Every event carries:

```json
{
  "schema_version": 2,
  "kind": "query | action | observation | answer | failure",
  "trace_id": "...",
  "span_id": "...",
  "parent_span_id": "... or null",
  "agent_id": "...",
  "run_id": "...",
  "ts": 1746291600.0
}
```

### Hierarchical QAOA Trace

The V2 evolution: every event carries `trace_id`, `span_id`, `parent_span_id`, and `agent_id`. Multi-agent delegation produces a nested span tree. V1 traces are auto-upgraded on load.

### SpanContext

Immutable carrier of `trace_id`, `span_id`, `parent_span_id`, `agent_id`. Propagated through execution trees. Use `child_span()` to create child spans for delegation.

### Span

Mutable accumulator for a single agent invocation: `token_count`, `model_latency_ms`, `tool_exec_ms`.

### Typed Event Bus

The `RuntimeEventBus` decouples the Core Runtime from all external observers. The runtime emits strongly-typed Pydantic events; the Workbench TUI (or any other subscriber) receives them without any coupling.

**All 14 event types:**

| Event | Emitted when |
|---|---|
| `RunStarted` | Agent loop begins |
| `AgentActivated` | A specific agent starts its loop (multi-agent) |
| `StreamChunkReceived` | A chunk of the final answer is ready |
| `ToolInvoked` | A tool call is dispatched |
| `ToolCompleted` | A tool call returns successfully |
| `ToolErrored` | A tool call fails or is denied by policy |
| `SpanOpened` | A new trace span is opened |
| `SpanClosed` | A trace span closes with metrics |
| `BudgetProgress` | Budget counters update (after each step/tool) |
| `CircuitBreakerTripped` | Circuit breaker threshold reached |
| `RunCompleted` | Agent loop finishes with an answer |
| `RunFailed` | Agent loop exits with a failure |
| `PatchMerged` | A Reflection Patch was auto-merged |
| `PatchRolledBack` | A previously merged patch was rolled back |

---

## Memory

### Dynamic Memory Engine

SQLite-backed (WAL mode) memory for Team Workspaces. The engine manages two namespaces:

- **Shared Memory** — tables with the `shared_` prefix; all agents in a team can read and write.
- **Private Memory** — tables with the `private_<agent_id>_` prefix; isolated at the SQL level.

### MemoryScope

The access layer for a single namespace. Enforces prefix rules at SQL parse time, not just at the application layer. Tools and agents work with logical table names; the scope handles physical prefixing.

### DDL Safelist

Schema changes through the Memory Schema Tool are validated before execution:

| Permitted | Forbidden |
|---|---|
| `CREATE TABLE` | `DROP TABLE` |
| `CREATE INDEX` | `DROP INDEX` |
| `ALTER TABLE ADD COLUMN` | `DELETE`, `TRUNCATE` (as DDL), `ALTER TABLE DROP COLUMN` |

Regular DML (`INSERT`, `SELECT`, `UPDATE`, `DELETE`) is permitted through `MemoryScope` directly.

### MemoryRetriever

Token-budgeted retrieval with keyword + recency ranking:

```
score = keyword_hits * 1_000_000 + created_timestamp
```

Results are wrapped as **Untrusted Observations** with provenance markers (`UNTRUSTED EVIDENCE START / END`).

---

## Multi-agent

### Tool-Based Delegation Model

The orchestrator receives auto-generated `delegate_to_<worker>` tools — one per worker agent defined in `naqsha.toml`. When the orchestrator calls `delegate_to_worker`, a nested `CoreRuntime` is spawned under a child `SpanContext`. No graph engine. No state machine. Just a tool call.

### Worker Isolation

The orchestrator's `AgentContext` is **never** passed to a worker. Worker private memory is inaccessible to the orchestrator. Delegation runs a fully isolated nested runtime.

---

## Autonomy

### Reflection Loop

Generates **Reflection Patches** from evaluated runs. A patch is an isolated workspace with a proposed code or configuration change. Before any merge, the **Reliability Gate** runs pytest over the gate paths.

### Automated Rollback Manager

Before any autonomous merge:

1. Snapshots `naqsha.toml` and workspace files to `.naqsha/backups/<stamp>/`.
2. Applies the merge.
3. Sets `boot_status = pending`.
4. On the next `naqsha run`, a boot probe verifies the workspace is healthy.
5. If the probe fails, the workspace is restored from snapshot and `PatchRolledBack` is emitted.

The manager prunes to the 5 most recent backups.

### `auto_merge`

**Always `false` by default.** Opt-in only in `naqsha.toml`:

```toml
[reflection]
enabled    = true
auto_merge = true  # requires reliability_gate = true
```

There is no bypass for the Reliability Gate. `auto_merge = true` without `reliability_gate = true` is silently ignored.

---

## Where to read more

- Product intent: [PRD (V2 runtime)](https://github.com/KM-Alee/naqsha/blob/main/docs/prd/0002-naqsha-v2-runtime.md)
- Architecture decisions: [ADRs](https://github.com/KM-Alee/naqsha/tree/main/docs/adr) (ADRs 0006–0019 define V2)
- Agent maintainer rules: [AGENTS.md](https://github.com/KM-Alee/naqsha/blob/main/AGENTS.md)
- Full glossary: [CONTEXT.md](https://github.com/KM-Alee/naqsha/blob/main/CONTEXT.md)

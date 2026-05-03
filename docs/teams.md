# Teams (Team Workspaces)

A **Team Workspace** is a directory whose root contains `naqsha.toml`. This single file defines the entire multi-agent topology: orchestrator and workers, their model adapters, tool allowlists, budget caps, memory settings, and reflection policy.

---

## The `naqsha.toml` format

### `[workspace]` — workspace metadata

```toml
[workspace]
name         = "research-team"   # human-readable label
orchestrator = "orch"            # agent_id of the orchestrator
auto_approve = false             # true → all write-tier tools auto-approved
```

### `[memory]` — shared memory engine

```toml
[memory]
db_path = ".naqsha/memory.db"   # SQLite file for the Dynamic Memory Engine
```

### `[reflection]` — autonomous improvement

```toml
[reflection]
enabled          = true    # enable Reflection Loop
auto_merge       = false   # ALWAYS false by default; opt-in only
reliability_gate = true    # run pytest before auto-merge
gate_paths       = ["tests/smoke/"]
```

### `[agents.<id>]` — agent definition

```toml
[agents.orch]
role          = "orchestrator"    # "orchestrator" or "worker"
model_adapter = "openai_compat"   # fake | openai_compat | anthropic | gemini | ollama
tools         = ["clock", "list_memory_tables"]   # strict allowlist
max_retries   = 3       # Circuit Breaker threshold
max_steps     = 20      # Budget: max steps
max_tokens    = 4096    # Budget: max tokens
```

### Adapter sub-tables

Each model adapter has its own configuration sub-table:

=== "openai_compat"

    ```toml
    [agents.orch.openai_compat]
    model       = "gpt-4o"
    api_base    = "https://api.openai.com/v1"
    api_key_env = "OPENAI_API_KEY"   # env var name, never the key value
    ```

=== "anthropic"

    ```toml
    [agents.orch.anthropic]
    model       = "claude-3-5-sonnet-20241022"
    api_key_env = "ANTHROPIC_API_KEY"
    ```

=== "gemini"

    ```toml
    [agents.orch.gemini]
    model       = "gemini-1.5-flash"
    api_key_env = "GOOGLE_API_KEY"
    ```

=== "ollama"

    ```toml
    [agents.orch.ollama]
    model    = "llama3.2"
    base_url = "http://localhost:11434"   # default; override for custom installs
    ```

=== "fake"

    ```toml
    [agents.orch.fake_model]
    messages = [
      { kind = "action", calls = [
        { id = "c1", name = "clock", arguments = {} },
      ]},
      { kind = "answer", text = "done" },
    ]
    ```

---

## Complete example

```toml
[workspace]
name         = "research-team"
orchestrator = "orch"
auto_approve = false

[memory]
db_path = ".naqsha/memory.db"

[reflection]
enabled          = true
auto_merge       = false
reliability_gate = true
gate_paths       = ["tests/"]

[agents.orch]
role          = "orchestrator"
model_adapter = "openai_compat"
tools         = ["clock", "list_memory_tables"]
max_steps     = 30
max_tokens    = 8192

[agents.orch.openai_compat]
model       = "gpt-4o"
api_base    = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"

[agents.researcher]
role          = "worker"
model_adapter = "openai_compat"
tools         = ["clock", "read_file", "list_files", "list_memory_tables", "memory_schema"]
max_retries   = 3
max_steps     = 15
max_tokens    = 4096

[agents.researcher.openai_compat]
model       = "gpt-4o-mini"
api_base    = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
```

---

## Topology API

```python
from naqsha.orchestration.topology import (
    parse_team_topology_file,
    parse_team_topology,
)

# Load from disk
topo = parse_team_topology_file(Path("naqsha.toml"))

# Load from an in-memory dict (tests and code generators)
topo = parse_team_topology({"workspace": {"name": "x", ...}, ...}, base_dir=Path("."))
```

`parse_team_topology` validates:

- At least one agent defined with `role = "orchestrator"`
- All `model_adapter` values are known types
- All tool names in `tools` lists are non-empty
- `Role-Based Tool Policy` names are consistent

It also **auto-injects** `delegate_to_<worker>` tools into the orchestrator's allowlist for each worker defined in the topology.

---

## Runtime builders

```python
from naqsha.orchestration.team_runtime import (
    build_team_orchestrator_runtime,
    build_worker_runtime,
    run_profile_for_topology_agent,
)
from naqsha import RuntimeEventBus

bus = RuntimeEventBus()

# Orchestrator runtime (includes delegation tools, shared memory)
rt = build_team_orchestrator_runtime(topo, workspace_path=Path("."), event_bus=bus)
result = rt.run("Analyse topic X")

# Worker runtime (used internally by delegation tools)
worker_rt = build_worker_runtime(topo, "researcher", workspace_path=Path("."), span_context=...)
```

---

## Tool-Based Delegation in detail

When `build_team_orchestrator_runtime` is called, NAQSHA:

1. Creates a `delegate_to_<worker>` tool for each worker in the topology.
2. Registers those tools in the orchestrator's `ToolRegistry`.
3. When the orchestrator calls `delegate_to_researcher(task="...")`:
   - A new `CoreRuntime` is spawned with the worker's profile.
   - A child `SpanContext` is created (same `trace_id`; new `span_id` with `parent_span_id` = orchestrator span).
   - The worker runs fully isolated — its `AgentContext` is created fresh; the orchestrator's context is **never** passed.
   - The worker's trace events share the same JSONL file, keyed by `agent_id = "researcher"`.
   - The worker's answer is returned to the orchestrator as a `ToolObservation`.
4. If the worker's Circuit Breaker trips, the observation carries `metadata["kind"] = "TaskFailedError"` and `metadata["circuit_breaker"] = True`.

---

## Role-Based Tool Policy

Each agent's `tools` array is its **complete allowlist**. Calling a tool not in the list:

1. The call is **denied** before execution.
2. A `ToolErrored` event is emitted on the Event Bus.
3. A denial observation is written to the trace.
4. The model receives the denial as a structured error observation.

There is no runtime way to escalate permissions. The allowlist is set at topology parse time.

---

## Worker isolation invariants

These invariants are **non-negotiable** and enforced by the runtime:

1. The orchestrator's `AgentContext` is **never** passed to a worker.
2. `private_<agent_id>_*` tables are inaccessible to other agents at the SQL level.
3. Workers cannot read or modify the orchestrator's private memory.
4. Delegation runs a fully isolated `CoreRuntime`; there is no shared mutable state.

---

## Hierarchical trace

All agents in a team write to the **same JSONL trace file**, distinguished by:

| Field | Orchestrator | Worker |
|---|---|---|
| `trace_id` | shared `run_id` | shared `run_id` |
| `agent_id` | `"orch"` | `"researcher"` |
| `span_id` | `"span_orch_..."` | `"span_researcher_..."` |
| `parent_span_id` | `null` | `"span_orch_..."` |

The Workbench TUI's **Span Tree** and **Flame Graph** panels reconstruct the hierarchy from these fields.

---

## Further reading

- API: [`naqsha.orchestration`](reference/orchestration.md)
- ADR: [0013 — Tool-Based Delegation Model](https://github.com/KM-Alee/naqsha/blob/main/docs/adr/0013-tool-based-delegation-model.md)
- ADR: [0012 — Multi-Agent Teams and Memory Scopes](https://github.com/KM-Alee/naqsha/blob/main/docs/adr/0012-multi-agent-teams-and-memory-scopes.md)
- Getting started: [Fake team example](getting-started.md#team-workspace-two-agent-fake-model-no-keys)

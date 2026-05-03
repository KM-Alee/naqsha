# Migration guide

---

## Migrating from NAQSHA 0.1.x to 0.2.0

Version 0.2.0 is a **major feature release** with an internal rewrite under the Domain-Driven `src/` layout. All **V1 public imports** remain stable — no import paths have been removed. However, a number of things have changed that you should be aware of.

### No breaking changes for library users

```python
# These still work exactly as before:
from naqsha import build_runtime, load_run_profile, AgentWorkbench
from naqsha import CoreRuntime, RuntimeConfig
from naqsha import agent, AgentContext
```

The flat public API in `naqsha/__init__.py` is unchanged.

### New public exports

```python
# V2 additions — all importable from the flat API:
from naqsha import (
    RuntimeEventBus,          # Typed Event Bus
    RunStarted, RunCompleted, RunFailed,
    ToolInvoked, ToolCompleted, ToolErrored,
    SpanOpened, SpanClosed,
    BudgetProgress,
    CircuitBreakerTripped,
    PatchMerged, PatchRolledBack,
    Span, SpanContext, create_root_span,
    TeamTopology,
)
```

### New domain package paths

Internal code has moved to domain packages. You can import from the flat API as before, **or** use the new paths directly:

| Old (still works) | New canonical path |
|---|---|
| `naqsha.runtime` | `naqsha.core.runtime` |
| `naqsha.policy` | `naqsha.core.policy` |
| `naqsha.scheduler` | `naqsha.core.scheduler` |
| `naqsha.budgets` | `naqsha.core.budgets` |
| `naqsha.approvals` | `naqsha.core.approvals` |
| `naqsha.trace.base` | `naqsha.tracing.store` |
| `naqsha.protocols.nap` | `naqsha.models.nap` |
| `naqsha.protocols.qaoa` | `naqsha.tracing.protocols.qaoa` |

### Trace format — V2 schema

All new runs write QAOA Trace **V2** with `schema_version: 2` and the new fields `trace_id`, `span_id`, `parent_span_id`, `agent_id`. Existing V1 traces are **auto-upgraded on load**:

- `run_id` becomes `trace_id`
- A generated `span_id` is assigned
- `parent_span_id` defaults to `null`
- `agent_id` defaults to `"agent"`

V1 trace files are never modified on disk — the upgrade is in-memory only.

### Tools — Decorator-Driven API

Class-based V1 tools continue to work via the `FunctionTool` path. New tools should use `@agent.tool`:

```python
# V1 (still works)
from naqsha.tools import FunctionTool
my_tool = FunctionTool(name="echo", schema={...}, fn=lambda args: args["msg"])

# V2 (recommended)
from naqsha.tools import agent, AgentContext

@agent.tool(risk_tier="read", description="Echo the message.")
def echo(message: str, ctx: AgentContext) -> str:
    return message
```

Bridge to the legacy runtime path with `decorated_to_function_tool`:

```python
from naqsha.tools.decorated_adapter import decorated_to_function_tool
function_tool = decorated_to_function_tool(echo)
```

### Memory — Dynamic Memory Engine

The V1 SimpleMem-Cross adapter remains functional. New workspaces should use the **Dynamic Memory Engine**:

```python
# V1 (still works for single-agent runs)
from naqsha import MemoryPort  # SimpleMem-Cross based

# V2 (multi-agent, DDL-safe, scoped)
from naqsha.memory import DynamicMemoryEngine
engine = DynamicMemoryEngine(".naqsha/memory.db")
shared = engine.get_shared_scope()
private = engine.get_private_scope("my-agent")
```

For multi-agent teams, the Dynamic Memory Engine is wired automatically from the `[memory]` block in `naqsha.toml`.

### Configuration — `naqsha.toml`

V1 JSON Run Profiles continue to work for single-agent runs. Multi-agent teams require `naqsha.toml`:

```bash
# Re-initialise an existing workspace
naqsha init
```

---

## V1 migration summary table

| Feature | V1 | V2 (0.2.0) |
|---|---|---|
| Tool definition | Class-based `FunctionTool` | `@agent.tool` decorator |
| Memory | SimpleMem-Cross (session) | `DynamicMemoryEngine` (SQLite) |
| Trace format | V1 QAOA (flat) | V2 QAOA (hierarchical, span-aware) |
| Multi-agent | Not supported | `naqsha.toml` team topology |
| Event observability | Not supported | 14-event `RuntimeEventBus` |
| Circuit Breaker | Not supported | Configurable per agent |
| Workbench TUI | Not supported | Textual TUI (`[tui]` extra) |
| Docs site | Markdown files only | MkDocs-Material at GitHub Pages |

---

## Further reading

- [V2 PRD](https://github.com/KM-Alee/naqsha/blob/main/docs/prd/0002-naqsha-v2-runtime.md) — user stories and implementation decisions
- [CHANGELOG](https://github.com/KM-Alee/naqsha/blob/main/CHANGELOG.md) — detailed list of additions and changes
- [V1 PRD (historical)](https://github.com/KM-Alee/naqsha/blob/main/docs/prd/0001-naqsha-v1-runtime.md)

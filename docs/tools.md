# Tools (Decorator-Driven API)

V2 tools are ordinary Python functions decorated with **`@agent.tool`**. JSON Schema (Draft 2020-12) is generated from type hints at **import time**; malformed signatures raise `ToolDefinitionError` immediately — not at runtime.

---

## Minimal example

```python
from naqsha.tools import agent, AgentContext

@agent.tool(risk_tier="read", description="Echo the message back.")
def echo(message: str, ctx: AgentContext) -> str:
    return f"{ctx.agent_id} says: {message}"
```

The `ctx: AgentContext` parameter is **injected** by the Core Runtime and **omitted** from the public schema exposed to models. The model never sees it.

---

## The `@agent.tool` decorator

```python
@agent.tool(
    risk_tier="read" | "write" | "side-effect",
    description="Human-readable description.",
    read_only=True,     # optional; inferred from risk_tier if not set
)
def my_tool(...) -> ...:
    ...
```

| Parameter | Type | Description |
|---|---|---|
| `risk_tier` | `str` | `"read"`, `"write"`, or `"side-effect"` |
| `description` | `str` | Shown to the model in the tool schema |
| `read_only` | `bool` | Optional override; defaults to `risk_tier == "read"` |

### Risk tiers

| Tier | Typical use | Default gate |
|---|---|---|
| `read` | Query data, compute, introspect | No approval required |
| `write` | Persist data, modify files | `InteractiveApprovalGate` in TTY mode |
| `side-effect` | External calls (email, webhooks, …) | Requires explicit approval |

---

## Supported type hints

| Python type | JSON Schema type |
|---|---|
| `str` | `string` |
| `int` | `integer` |
| `float` | `number` |
| `bool` | `boolean` |
| `Optional[T]` | nullable `T` |
| `list[T]` | `array` with item schema |
| `dict[str, T]` | `object` with `additionalProperties` |
| Pydantic `BaseModel` subclass | `object` with full schema |
| `AgentContext` | injected; omitted from schema |

Any unresolvable or unsupported type hint raises `ToolDefinitionError` at decoration time.

---

## AgentContext

`AgentContext` is the **only** stable public API for tools to access runtime state. No global variables.

```python
from naqsha.tools import agent, AgentContext

@agent.tool(risk_tier="write", description="Store a note.")
def save_note(content: str, ctx: AgentContext) -> str:
    scope = ctx.shared_memory
    if scope is None:
        return "No memory configured."
    scope.execute(
        "INSERT INTO shared_notes (content, created_ts) VALUES (?, strftime('%s','now'))",
        (content,),
    )
    return "Saved."
```

| Field | Type | Description |
|---|---|---|
| `agent_id` | `str` | Current agent identifier |
| `run_id` | `str` | Unique run identifier |
| `workspace_path` | `Path \| None` | Workspace root; `None` for in-memory runs |
| `shared_memory` | `MemoryScope \| None` | Team-wide memory (`shared_*` prefix) |
| `private_memory` | `MemoryScope \| None` | Agent-private memory (`private_<agent_id>_*`) |
| `span` | `Span \| None` | Active trace span (for custom metric recording) |

---

## Pydantic model parameters

Complex structured parameters are best expressed as Pydantic models:

```python
from naqsha.tools import agent, AgentContext
from pydantic import BaseModel, Field

class SearchParams(BaseModel):
    query: str = Field(description="The search query.")
    limit: int = Field(default=10, ge=1, le=100, description="Max results.")

@agent.tool(risk_tier="read", description="Search the knowledge base.")
async def search_kb(params: SearchParams, ctx: AgentContext) -> list[dict]:
    scope = ctx.shared_memory
    if scope is None:
        return []
    rows = scope.query(
        "SELECT title, snippet FROM shared_articles WHERE snippet LIKE ? LIMIT ?",
        (f"%{params.query}%", params.limit),
    )
    return [{"title": r[0], "snippet": r[1]} for r in rows]
```

The Pydantic schema (including `Field` descriptions and validators) is merged into the generated JSON Schema.

---

## Async tools

`async def` tools are fully supported. The `ToolExecutor` handles coroutines transparently:

```python
@agent.tool(risk_tier="side-effect", description="Send a webhook notification.")
async def notify(url: str, message: str, ctx: AgentContext) -> str:
    import urllib.request, json
    data = json.dumps({"text": message}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return f"Sent ({r.status})"
```

---

## ToolRegistry and ToolExecutor

### ToolRegistry

```python
from naqsha.tools import ToolRegistry, agent

registry = ToolRegistry()

@agent.tool(risk_tier="read", description="Get current time.")
def clock(ctx: AgentContext) -> str:
    from datetime import datetime, UTC
    return datetime.now(UTC).isoformat()

registry.register(clock)

# Export schemas for a model adapter
schemas = registry.get_schemas()
```

### ToolExecutor

```python
from naqsha.tools import ToolExecutor, AgentContext

executor = ToolExecutor(registry)
ctx = AgentContext(agent_id="orch", run_id="r1")

# Execute a tool by name
observation = executor.execute("clock", {}, ctx)
print(observation.payload)  # "2026-05-03T17:00:00+00:00"
```

On any exception, `ToolExecutor` returns a structured `ToolObservation` with `metadata["tool_error"] = True` — the exception never propagates to the Core Runtime.

---

## Bridging to the runtime

The legacy `FunctionTool` path used by `build_runtime` profiles is bridged via `decorated_to_function_tool`:

```python
from naqsha.tools.decorated_adapter import decorated_to_function_tool

function_tool = decorated_to_function_tool(clock)
# → can be passed directly to RuntimeConfig.tools
```

---

## Starter Tool Set

NAQSHA ships a set of ready-to-use tools in `naqsha.tools.starter`. These are all defined with `@agent.tool` and are used by the default profiles:

| Tool | Risk tier | Description |
|---|---|---|
| `clock` | `read` | Return the current UTC time |
| `list_files` | `read` | List files in a directory |
| `read_file` | `read` | Read a file's contents |
| `write_file` | `write` | Write content to a file |
| `memory_schema` | `write` | Execute DDL schema changes (safelist enforced) |
| `list_memory_tables` | `read` | List all memory tables accessible to this agent |

---

## Further reading

- API: [`naqsha.tools`](reference/tools.md)
- ADR: [0009 — Decorator-Driven API](https://github.com/KM-Alee/naqsha/blob/main/docs/adr/0009-decorator-driven-api.md)

# Memory (Dynamic Memory Engine)

NAQSHA's **Dynamic Memory Engine** is a SQLite-backed (WAL mode) knowledge store for **Team Workspaces**. It provides strictly isolated **Shared Memory** and **Private Memory** namespaces, a DDL safelist, and token-budgeted retrieval.

---

## Overview

```python
from naqsha.memory import DynamicMemoryEngine

engine = DynamicMemoryEngine(".naqsha/memory.db")

# Team-wide tables (shared_* prefix)
shared = engine.get_shared_scope()

# Agent-private tables (private_<agent_id>_* prefix)
private = engine.get_private_scope("my-agent")
```

The engine opens the SQLite file in WAL mode with `check_same_thread=False`, so tools invoked from the Tool Scheduler's thread pool can safely use the same connection.

---

## Memory scopes

### Shared Memory

All agents in a team can read and write `shared_*` tables:

```python
shared = engine.get_shared_scope()

# Create a table (DDL safelist enforced)
shared.execute("""
    CREATE TABLE IF NOT EXISTS shared_notes (
        id         INTEGER PRIMARY KEY,
        agent_id   TEXT NOT NULL,
        content    TEXT NOT NULL,
        created_ts INTEGER NOT NULL DEFAULT (strftime('%s','now'))
    )
""")

# Write a note
shared.execute(
    "INSERT INTO shared_notes (agent_id, content) VALUES (?, ?)",
    ("researcher", "Finding: X implies Y"),
)

# Query notes
rows = shared.query("SELECT agent_id, content FROM shared_notes ORDER BY created_ts DESC")
for agent_id, content in rows:
    print(f"[{agent_id}] {content}")
```

### Private Memory

Only the owning agent can access `private_<agent_id>_*` tables. No other agent can query or even list them — enforced at the SQL prefix level, not just application logic:

```python
private = engine.get_private_scope("researcher")

private.execute("""
    CREATE TABLE IF NOT EXISTS private_researcher_scratch (
        id      INTEGER PRIMARY KEY,
        key     TEXT NOT NULL,
        value   TEXT NOT NULL
    )
""")

private.execute("INSERT INTO private_researcher_scratch (key, value) VALUES (?, ?)", ("plan", "..."))
```

If `researcher` tries to access `private_orch_*` tables via the `orch` scope, the scope raises `ValueError` at prefix validation time — before any SQL reaches the database.

---

## DDL safelist

Schema changes are validated before execution. The safelist permits:

| Permitted | Example |
|---|---|
| `CREATE TABLE` | `CREATE TABLE IF NOT EXISTS shared_notes (...)` |
| `CREATE INDEX` | `CREATE INDEX idx_notes_ts ON shared_notes(created_ts)` |
| `ALTER TABLE ADD COLUMN` | `ALTER TABLE shared_notes ADD COLUMN tags TEXT` |

Everything else is **rejected** with `ForbiddenDDLError`:

```python
from naqsha.memory.ddl import ForbiddenDDLError

try:
    shared.execute("DROP TABLE shared_notes")
except ForbiddenDDLError as e:
    print(e)  # DROP TABLE is not permitted by the DDL safelist
```

Regular DML (`INSERT`, `SELECT`, `UPDATE`, `DELETE`) is **always permitted** through `MemoryScope` directly. The safelist only applies to schema-changing statements.

---

## Transactions

`MemoryScope` supports explicit transaction management:

```python
scope.begin()
try:
    scope.execute("INSERT INTO shared_notes (agent_id, content) VALUES (?, ?)", ("orch", "a"))
    scope.execute("INSERT INTO shared_notes (agent_id, content) VALUES (?, ?)", ("orch", "b"))
    scope.commit()
except Exception:
    scope.rollback()
    raise
```

---

## Token-budgeted retrieval

The `MemoryRetriever` fetches relevant rows from a table and wraps the results as **Untrusted Observations** with provenance markers:

```python
from naqsha.memory import MemoryRetriever

retriever = MemoryRetriever(
    scope=shared,
    token_budget=512,   # approximate; ~4 chars per token
    table="shared_notes",
    content_column="content",
)

results = retriever.retrieve("what implies Y")
# Returns a string like:
#
# --- UNTRUSTED EVIDENCE START ---
# [shared_notes row 3] Finding: X implies Y
# --- UNTRUSTED EVIDENCE END ---
```

### Ranking formula

```
score = keyword_hits * 1_000_000 + created_timestamp
```

Keyword matches always dominate recency. Results are deduplicated and trimmed to fit within `token_budget`.

---

## Memory Schema Tool

Agents can evolve their own schema using the `memory_schema` tool (decorated with `@agent.tool`):

```python
# In a tool call from the model:
memory_schema(
    sql="CREATE TABLE IF NOT EXISTS shared_research (id INTEGER PRIMARY KEY, topic TEXT, summary TEXT, created_ts INTEGER)",
    ctx=ctx,
)
```

The tool validates the DDL against the safelist before execution, providing a clear error message if the statement is forbidden. The model can then adapt its approach.

---

## Team memory configuration

For multi-agent teams, a single shared SQLite file is opened with `open_team_memory_engine`:

```python
from naqsha.memory.sharing import open_team_memory_engine, TeamMemoryConfig

config = TeamMemoryConfig(db_path=Path(".naqsha/memory.db"))
engine = open_team_memory_engine(config)
```

This is wired automatically by `build_team_orchestrator_runtime` from the `[memory]` section of `naqsha.toml`.

---

## Optional embeddings (sqlite-vec)

Install the `[memory]` extra:

```bash
pip install "naqsha[memory]"
```

Enable in the engine:

```python
engine = DynamicMemoryEngine(".naqsha/memory.db", enable_embeddings=True)
```

When enabled, the retriever can perform semantic ranking in addition to keyword + recency. Configure in `naqsha.toml`:

```toml
[memory]
db_path           = ".naqsha/memory.db"
enable_embeddings = true
```

---

## Listing tables

```python
# All tables in the shared namespace
tables = shared.list_tables()
print(tables)  # ["shared_notes", "shared_research"]

# All tables across all namespaces (admin view)
all_tables = engine.list_all_tables()
```

---

## Further reading

- API: [`naqsha.memory`](reference/memory.md)
- ADR: [0011 — Dynamic Memory Engine](https://github.com/KM-Alee/naqsha/blob/main/docs/adr/0011-dynamic-memory-engine.md)
- ADR: [0012 — Multi-Agent Teams and Memory Scopes](https://github.com/KM-Alee/naqsha/blob/main/docs/adr/0012-multi-agent-teams-and-memory-scopes.md)

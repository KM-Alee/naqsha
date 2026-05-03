# NAQSHA

NAQSHA is a minimal agent runtime context for building a production-shaped ReAct executor with durable memory and strict tool contracts.

## Language

**NAQSHA**:
A minimal Python agent runtime whose core owns agent execution, trace events, tool contracts, memory hooks, and runtime guardrails.
_Avoid_: NAQSH, platform, app, hosted service

**Core Runtime**:
The inspectable NAQSHA library surface that executes agent runs and exposes extension points for tools, memory, tracing, and safety policy.
_Avoid_: line-count target, tiny demo

**Adapter**:
An integration layer that exposes NAQSHA through a specific interface without owning the core runtime semantics.
_Avoid_: core feature, platform requirement

**V1 Interface Set**:
The first supported ways to use NAQSHA: Python library and CLI.
_Avoid_: hosted platform, UI product, MCP adapter

**Team Workspace**:
A self-contained directory containing a team of agents (or a single agent), their topology, Run Profile, shared and private memory, traces, and custom tools.
_Avoid_: single-agent only folder

**Agent Workbench**:
The CLI and library workflows that wrap the Core Runtime: initialize an agent project, run queries, inspect **QAOA Traces**, replay and evaluate runs, and generate **Reflection Patches** for reviewed self-improvement.
_Avoid_: conflating workbench UX with Core Runtime execution rules

**Role-Based Tool Policy**:
The security model within a Team Workspace where each sub-agent is granted a strict, specific subset of tools based on its role.
_Avoid_: all agents having all tools

**Dynamic Memory Engine**:
The V2 memory backend (backed by SQLite) that supports both **Shared Memory** (accessible by all agents in a team) and **Private Memory** (isolated to a specific agent), allowing autonomous DDL schema evolution and optional `sqlite-vec` embeddings.
_Avoid_: static session-based memory only

**MkDocs Documentation Engine**:
The official documentation framework for V2, using MkDocs-Material and mkdocstrings to automatically generate beautiful, searchable developer documentation from Python docstrings and type hints.
_Avoid_: raw markdown files without a static site generator

**Domain-Driven src/ Layout**:
The physical codebase structure for V2 that enforces architectural boundaries. The `src/naqsha/` directory is divided into strict domains (`core`, `models`, `tools`, `memory`, `orchestration`, `tracing`, `reflection`, `tui`) to ensure decoupling and maintainability.
_Avoid_: flat file structures, circular dependencies between core and UI

**Structured Error Escalation**:
The error handling pattern where tool exceptions are caught and returned to the agent as structured observations. If an agent fails repeatedly, a Circuit Breaker trips and escalates the failure to the Orchestrator.
_Avoid_: crashing the process on minor errors, silent infinite loops

**Circuit Breaker**:
A safety mechanism that stops an agent if it repeatedly encounters the same error or exhausts its retry budget, preventing runaway costs.

**Strict Internal Protocol (NAP V2)**:
The internal communication standard of the Core Runtime. The runtime only speaks NAP V2; all provider-specific quirks are handled by isolated, thin Model Adapters.
_Avoid_: provider-specific logic in the core runtime, heavy third-party translation libraries

**Context-Aware Dependency Injection**:
The pattern used in the Decorator-Driven API where the Core Runtime automatically injects runtime state (like `AgentContext`, memory connections, or trace spans) into a tool function if the developer includes it in the type signature.
_Avoid_: global variables for tool state

**Typed Event Bus**:
The decoupling mechanism in V2 where the Core Runtime emits strongly-typed Pydantic events (e.g., `ToolInvoked`, `SpanCompleted`) instead of printing directly. The Workbench TUI (or any other adapter) subscribes to these events to render live updates.
_Avoid_: hardcoding CLI/TUI logic into the core library

**Decorator-Driven API**:
The developer-friendly interface in V2 that uses Python decorators (e.g., `@agent.tool`) and type hints to automatically generate strict tool schemas and policies under the hood.
_Avoid_: verbose class inheritance for tools

**Workbench TUI**:
The rich Terminal User Interface (TUI) that powers the Agent Workbench, providing interactive wizards for agent creation, visual management, and analytics directly in the terminal.
_Avoid_: plain text CLI, local web dashboard

**Tool-Based Delegation Model**:
The mechanism for multi-agent orchestration where the Core Runtime automatically generates tools (e.g., `delegate_to_coder`) for the orchestrator, allowing sub-agents to be invoked as standard tool calls without requiring a complex graph or state machine.
_Avoid_: heavy graph routers, complex message buses

**Python Package**:
The distributable NAQSHA library and CLI artifact intended for PyPI release under the `naqsha` distribution name.
_Avoid_: local script, unpublished prototype

**Packaging Baseline**:
The Python packaging setup for NAQSHA: `pyproject.toml`, Hatchling build backend, `uv` development workflow, and optional extras.
_Avoid_: ad hoc setup.py, Poetry-only workflow

**Memory Port**:
The Core Runtime contract for reading and writing durable agent memory during a run.
_Avoid_: chat history, context stuffing

**Model Client**:
The Core Runtime contract for requesting the next validated NAP message from a model provider.
_Avoid_: OpenAI client, raw provider response

**SimpleMem-Cross Adapter**:
The default local Adapter that implements the Memory Port using SimpleMem-Cross session lifecycle and persistence.
_Avoid_: hosted memory service, MCP default

**Hierarchical QAOA Trace**:
The V2 evolution of the QAOA Trace that includes `span_id`, `parent_span_id`, and `agent_id` to support OpenTelemetry-style tracing across multi-agent teams. This enables the Workbench TUI to render flame graphs and detailed token/time analytics.
_Avoid_: flat, unreadable trace logs for multi-agent runs

**Trace Store**:
The persistence boundary for QAOA Traces, defaulting to append-only JSONL files in v1.
_Avoid_: memory database, provider logs

**Observation Sanitizer**:
The runtime filter that redacts secret-like or policy-forbidden content before observations enter traces, memory, or prompts.
_Avoid_: raw persistence, best-effort cleanup

**NAP Action**:
The strict model-facing action envelope that requests tool calls or returns a final answer.
_Avoid_: free-form instruction, chain-of-thought

**Tool Scheduler**:
The Core Runtime component that decides whether approved tool calls execute serially or in parallel.
_Avoid_: implicit batching, provider execution order

**Tool Policy**:
The runtime rules that decide which tools a run may call and which approvals are required.
_Avoid_: prompt-only safety, informal guardrails

**Approval Gate**:
The Tool Policy checkpoint that requires explicit human or callback approval before high-risk side effects execute.
_Avoid_: notification, audit log only

**Budget Limit**:
An enforced cap on steps, tokens, tool calls, wall-clock time, or per-tool execution time.
_Avoid_: tuning hint, soft warning

**Untrusted Observation**:
Tool output that may inform the model but must never be treated as instructions to the runtime.
_Avoid_: tool instruction, trusted context

**Starter Tool Set**:
The tools NAQSHA ships as first-party examples and adapters for v1.
_Avoid_: always-allowed tools, agent permissions

**Allowed Tool**:
A tool that Tool Policy permits for a specific run.
_Avoid_: installed tool, available capability

**Reliability Gate**:
The v1 acceptance bar covering replay, tool policy, memory recall, and OWASP-mapped red-team tests.
_Avoid_: demo checklist, happy-path test

**Runtime Slice**:
The first milestone proving deterministic execution, NAP validation, QAOA tracing, tool policy, scheduling, and basic tools without memory or reflection.
_Avoid_: vertical demo, full v1

**Run Profile**:
A named configuration for model adapter, tools, budgets, memory, trace location, and approval behavior.
_Avoid_: hidden defaults, environment-only config

**Reflection Loop**:
The mechanism that turns evaluated run outcomes into reusable behavior guidance or autonomous code updates.
_Avoid_: hidden learning, passive notes

**Reflection Patch**:
A code change generated by the Reflection Loop. In V2, this may be automatically merged if it passes the Reliability Gate, subject to the Automated Rollback Manager.
_Avoid_: unverified hotpatch

**V2 Runtime**:
The next generation of NAQSHA that allows agents to autonomously evolve their codebase using an Automated Rollback Manager.
_Avoid_: V1 constraints

**Automated Rollback Manager**:
The safety mechanism that monitors an agent after an autonomous code update and reverts to the last known good state if the runtime crashes or fails to boot.
_Avoid_: manual recovery only

## Relationships

- **NAQSHA** contains exactly one **Core Runtime**.
- **NAQSHA** may have many **Adapters**.
- An **Adapter** depends on the **Core Runtime**, not the other way around.
- The **V1 Interface Set** exposes the **Core Runtime** without changing its semantics.
- The **Python Package** delivers the **V1 Interface Set**.
- The **Packaging Baseline** produces the **Python Package**.
- The **Core Runtime** owns the **Memory Port**.
- The **Core Runtime** owns the **Model Client** port.
- The **SimpleMem-Cross Adapter** implements the **Memory Port**.
- The **Core Runtime** persists each run as a **QAOA Trace**.
- The **Trace Store** stores **QAOA Traces**.
- The **Observation Sanitizer** processes **Untrusted Observations** before persistence or model reinjection.
- A **QAOA Trace** contains zero or more **NAP Actions**.
- The **Core Runtime** enforces **Tool Policy** before executing a **NAP Action**.
- An **Approval Gate** blocks high-risk **Allowed Tools** until approved.
- A **Budget Limit** fails closed when exhausted.
- The **Tool Scheduler** executes approved calls from a **NAP Action**.
- Each tool call returns an **Untrusted Observation**.
- The **Starter Tool Set** may include tools that are not **Allowed Tools** for a given run.
- The **Reliability Gate** validates **QAOA Trace**, **Tool Policy**, and **Memory Port** behavior.
- The **Runtime Slice** precedes SimpleMem-Cross integration and the **Reflection Loop**.
- A **Run Profile** selects adapters and runtime limits without changing the **Core Runtime**.
- The **Reflection Loop** must pass through the **Reliability Gate** before changing runtime behavior.
- The **Reflection Loop** may create a **Reflection Patch**, but human approval is required before it changes the active runtime.

## Example dialogue

> **Dev:** "Should the MCP server be part of NAQSHA v1?"
> **Domain expert:** "No — the **Core Runtime** should support memory and tool interfaces cleanly; MCP can be an **Adapter** around that runtime."

## Flagged ambiguities

- "Small core" originally implied a hard line-count requirement; resolved: the goal is an inspectable **Core Runtime**, not a specific LOC limit.
- "SimpleMem integration" could mean embedded library, SimpleMem-Cross, or hosted MCP; resolved: v1 uses a **Memory Port** with a local **SimpleMem-Cross Adapter** as the default.
- "ReAct trace" could imply storing private reasoning; resolved: NAQSHA stores **QAOA Trace** events and **NAP Actions**, not chain-of-thought.
- "Tool safety" could mean prompt instructions; resolved: NAQSHA uses enforced **Tool Policy** and treats all tool output as **Untrusted Observation**.
- "Default tools" could mean installed tools or allowed tools; resolved: v1 ships and allows the **Starter Tool Set** by default, while high-risk side effects still require approvals under **Tool Policy**.
- "Multiple tool calls" could imply automatic parallelism; resolved: the **Tool Scheduler** only runs calls in parallel when they are read-only, independent, and policy-approved.
- "Trace persistence" could mean sharing SimpleMem-Cross storage; resolved: v1 uses a separate **Trace Store** backed by append-only JSONL files.
- "Provider support" could mean OpenAI-compatible APIs in the core; resolved: providers are **Adapters** behind the **Model Client** port.
- "Done" could mean a working demo; resolved: v1 must pass the **Reliability Gate**.
- "First milestone" could mean memory-first or tool-breadth-first; resolved: build the **Runtime Slice** first.
- "Reflection" could mean passive post-run notes or active behavior changes; resolved: v1 includes an active-by-default **Reflection Loop** that may create **Reflection Patches** in isolation after tests, but cannot merge or hotpatch without human approval.
- "MCP support" could mean core dependency or adapter; resolved: MCP is deferred from the **V1 Interface Set**.
- "Python first" could mean local-only code; resolved: NAQSHA is a **Python Package** intended for PyPI.
- "PyPI name" could mean reusing `naqsh`; resolved: the intended distribution name is `naqsha` because `naqsh` is already taken on PyPI.
- "Project name" could mean keeping NAQSH while publishing `naqsha`; resolved: public project, package, CLI, and import name are all `naqsha` / NAQSHA.
- "Packaging" could mean any Python toolchain; resolved: use the **Packaging Baseline** with Hatchling, `uv`, console script `naqsha`, and optional extras.
- "Approval" could mean logging after the fact; resolved: an **Approval Gate** blocks high-risk side effects before execution.
- "Observation storage" could mean raw tool output everywhere; resolved: the **Observation Sanitizer** runs before traces, memory, and prompt reinjection.
- "Runtime limits" could mean recommendations; resolved: **Budget Limits** are hard caps that fail closed.
- "Configuration" could mean hidden environment variables; resolved: **Run Profiles** make model, tool, memory, trace, approval, and budget choices explicit.

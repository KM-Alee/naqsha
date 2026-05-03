# 0019 Domain-Driven src/ Layout

In NAQSHA V2, to support the framework's growth into an industry-standard Python library and enforce our strict architectural boundaries, we adopt a **Domain-Driven src/ Layout**.

The codebase will be structured under `src/naqsha/` and divided into isolated domain packages:
- `core/`: The headless engine, Event Bus, and runtime loop.
- `models/`: NAP V2 protocol and Thin Adapters.
- `tools/`: Decorator API and Dependency Injection.
- `memory/`: Dynamic Memory Engine (SQLite/sqlite-vec).
- `orchestration/`: Team topology and Tool-Based Delegation.
- `tracing/`: Hierarchical QAOA Trace.
- `reflection/`: Autonomous updates and the Automated Rollback Manager.
- `tui/`: The Textual/Rich CLI application.

This structure guarantees that the public API remains clean (exposed via `__init__.py`), makes the codebase highly navigable for contributors, and strictly enforces decoupling (e.g., the `core` package will never import from the `tui` package).

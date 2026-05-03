# 0015 Typed Event Bus for Library-CLI Decoupling

In NAQSHA V2, to maintain a pure, headless Core Runtime that can be embedded anywhere (CLI, FastAPI, etc.), we adopt a **Typed Event Bus** pattern. 

The Core Runtime will not contain any `print()` statements or TUI-specific logic. Instead, as the agent executes, the runtime yields or broadcasts strongly-typed Pydantic events (e.g., `AgentStarted`, `StreamChunkReceived`, `ToolInvoked`, `SpanCompleted`). 

The Workbench TUI acts as a subscriber to this event bus. It listens to the stream of events and updates its reactive terminal widgets (chat windows, flame graphs, token counters) in real-time. This ensures the library remains elegant and decoupled while the CLI provides a highly reactive, beautiful user experience.

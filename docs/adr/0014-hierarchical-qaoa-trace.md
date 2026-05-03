# 0014 Hierarchical QAOA Trace for Multi-Agent Analytics

In NAQSHA V2, to support advanced visual analytics in the Workbench TUI and to properly trace execution across multi-agent teams, we upgrade the trace format to a **Hierarchical QAOA Trace**. 

Instead of a flat list of events, every trace event now includes a `span_id`, a `parent_span_id`, and an `agent_id` (similar to OpenTelemetry). When an orchestrator delegates to a worker agent, a new child span is created. This allows the CLI to render flame graphs, expandable tree views, and accurate token/time attribution per agent, making complex team executions easy to debug and analyze.

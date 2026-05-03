# 0013 Tool-Based Delegation Model for Multi-Agent Orchestration

In NAQSHA V2, to support multi-agent teams without bloating the Core Runtime with complex graph routing or state machines (like LangGraph or AutoGen), we adopt a **Tool-Based Delegation Model**. 

When a Team Workspace is initialized with multiple agents, the framework automatically generates delegation tools for the orchestrator (e.g., `delegate_to_qa(task: str)`). When the orchestrator calls this tool, the Core Runtime pauses the orchestrator, executes the sub-agent's loop to completion, and returns the sub-agent's final answer as the tool's observation. This keeps the core execution loop simple and unified: multi-agent orchestration is just standard tool calling under the hood.

# 0012 Multi-Agent Teams with Shared and Private Memory

In NAQSHA V2, the fundamental unit of deployment shifts from a single agent to a **Team Workspace**. A workspace can contain a single agent or a topology of multiple agents (e.g., Orchestrator, Coder, QA). 

To support this safely and efficiently:
1. **Role-Based Tool Policies**: Each agent in the team is granted a strict subset of tools based on its role, preventing a worker agent from escalating privileges.
2. **Dual-Scope Memory**: The Dynamic Memory Engine provides both **Shared Memory** (a common database namespace where agents can collaborate on data without stuffing context windows) and **Private Memory** (an isolated namespace for an individual agent's scratchpad and internal state).
3. **Topology Definition**: The team structure and routing rules are defined in the workspace's `naqsha.toml` configuration.

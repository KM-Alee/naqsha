# 0018 Structured Error Escalation and Circuit Breakers

In NAQSHA V2, to ensure multi-agent teams are both resilient to minor errors and protected against infinite loops (which burn token budgets), we adopt a **Structured Error Escalation** pattern combined with **Circuit Breakers**.

1. **Tool-Level Recovery**: When a tool throws an exception, the Core Runtime catches it and returns a structured `ToolErrorObservation` to the active agent, allowing it to self-correct.
2. **Circuit Breaker**: If an agent repeatedly fails (e.g., hitting the same error consecutively or exhausting a retry budget), the runtime trips a circuit breaker. The agent's execution is halted to prevent runaway token spend.
3. **Orchestrator Recovery**: The failure is escalated to the calling Orchestrator as a `TaskFailedError`. The Orchestrator can then decide to attempt a different strategy, delegate to another worker, or gracefully report the failure to the user.

This pattern ensures the framework does not crash on minor API timeouts or bad JSON, but strictly bounds the blast radius of a confused agent.

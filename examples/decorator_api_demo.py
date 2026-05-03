"""
Demonstration of the NAQSHA V2 Decorator-Driven API.

This example shows how to define tools using the @agent.tool decorator,
register them, and execute them with automatic context injection.
"""

from pathlib import Path

from naqsha import AgentContext, RiskTier, ToolExecutor, ToolRegistry, agent


# Define tools using the decorator
@agent.tool(description="Add two numbers")
def add(a: int, b: int) -> str:
    """Add two numbers and return the result."""
    return f"The sum of {a} and {b} is {a + b}"


@agent.tool(risk_tier=RiskTier.READ_ONLY)
def greet(name: str, ctx: AgentContext) -> str:
    """Greet a user with context information."""
    return f"Hello {name}! You are running in workspace: {ctx.workspace_path}"


@agent.tool(risk_tier=RiskTier.WRITE, description="Write to a file")
async def write_message(message: str, ctx: AgentContext) -> str:
    """Write a message (async example)."""
    # In a real implementation, this would write to a file
    return f"Would write '{message}' to {ctx.workspace_path}/message.txt"


def main():
    """Demonstrate the decorator-driven API."""
    print("=" * 60)
    print("NAQSHA V2 Decorator-Driven API Demo")
    print("=" * 60)
    print()

    # Create a registry and register tools
    registry = ToolRegistry()
    registry.register(add)
    registry.register(greet)
    registry.register(write_message)

    print("Registered tools:")
    for name in sorted(registry.names()):
        tier = registry.get_risk_tier(name)
        readonly = "read-only" if registry.is_read_only(name) else "write"
        print(f"  - {name} ({tier}, {readonly})")
    print()

    # Export schemas (what would be sent to the model)
    print("Exported schemas for Model Adapter:")
    schemas = registry.export_schemas()
    for schema in schemas:
        print(f"  - {schema['name']}: {schema['description']}")
        print(f"    Parameters: {list(schema['parameters']['properties'].keys())}")
    print()

    # Create a context
    context = AgentContext(
        shared_memory=None,
        private_memory=None,
        span=None,
        workspace_path=Path("/tmp/demo-workspace"),
        agent_id="demo-agent",
        run_id="demo-run-001",
    )

    # Create an executor
    executor = ToolExecutor(context)

    # Execute tools
    print("Executing tools:")
    print()

    # Execute add (no context needed)
    add_func = registry.get("add")
    result1 = executor.execute(add_func, {"a": 10, "b": 32})
    print("add(10, 32):")
    print(f"  ok: {result1.ok}")
    print(f"  content: {result1.content}")
    print()

    # Execute greet (context injected automatically)
    greet_func = registry.get("greet")
    result2 = executor.execute(greet_func, {"name": "Alice"})
    print("greet('Alice'):")
    print(f"  ok: {result2.ok}")
    print(f"  content: {result2.content}")
    print()

    # Execute async tool (note: in real code, you'd await this)
    write_func = registry.get("write_message")
    result3_coro = executor.execute(write_func, {"message": "Hello World"})
    print("write_message('Hello World') [async]:")
    print(f"  Returns coroutine: {result3_coro}")
    print("  (In real code, you would: result = await executor.execute(...))")
    print()

    print("=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()

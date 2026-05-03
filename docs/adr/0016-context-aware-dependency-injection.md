# 0016 Context-Aware Dependency Injection for Tools

In NAQSHA V2, to allow custom tools to interact with the runtime (e.g., querying the Dynamic Memory Engine, logging custom trace spans) without resorting to global state, we adopt **Context-Aware Dependency Injection**.

When a developer defines a tool using the `@agent.tool` decorator, they can optionally include specific typed parameters in the function signature, such as `ctx: AgentContext`. Before executing the tool, the Core Runtime inspects the signature using Python's `inspect` module. If it detects requested dependencies, it injects the live, thread-safe instances into the function call. If the tool does not need runtime context, the developer simply omits the parameter, keeping the tool function clean and simple. This ensures state safety in concurrent or multi-agent environments.

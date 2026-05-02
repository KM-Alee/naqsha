# Enforce Tool Policy in the Runtime

NAQSHA will enforce tool risk tiers, per-run allowlists, schema validation, and approval gates in the **Core Runtime** before executing tool calls. The v1 **Starter Tool Set** is allowed by default so the runtime is useful out of the box, but high-risk side effects still require approval gates; this makes prompt injection, improper output handling, excessive agency, and unbounded consumption controls observable and testable, at the cost of requiring every tool integration to declare policy metadata up front.

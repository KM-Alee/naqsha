# 0017 Strict Internal Protocol with Thin Model Adapters

In NAQSHA V2, to support diverse multi-agent teams where different agents may use different models (e.g., Claude for the Orchestrator, local Ollama for a Worker), we must isolate provider-specific API quirks from the Core Runtime. 

We adopt a **Strict Internal Protocol (NAP V2) with Thin Adapters** pattern. The Core Runtime never interacts with provider APIs directly and does not contain provider-specific logic. Instead, it communicates exclusively using the internal Network Action Protocol (NAP V2). Thin, isolated Model Adapters (e.g., `OpenAIAdapter`, `AnthropicAdapter`) are responsible for translating NAP requests into provider-specific HTTP calls and translating the responses back into validated NAP objects. This keeps the core pure and allows developers to easily plug in custom or emerging models without modifying the framework.

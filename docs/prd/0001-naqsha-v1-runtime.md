# NAQSHA V1 Runtime PRD

## Problem Statement

Developers who want to build useful agent applications face a bad trade-off: either they adopt a heavy framework whose behavior is hard to inspect, or they assemble brittle scripts that lack durable memory, replayability, policy enforcement, and production-grade failure behavior. The result is agent code that can appear impressive in a demo but becomes difficult to debug, secure, test, or evolve once tools, memory, and real user workflows enter the system.

NAQSHA should solve this by providing an inspectable Python agent runtime with an explicit ReAct loop, strict NAP Action validation, QAOA Trace persistence, first-class memory integration, enforced Tool Policy, and a practical CLI. The product must feel small enough to understand, but not small in the sense of being incomplete or demo-only. The measure of success is not line count; it is whether the Core Runtime is deterministic, replayable, safe by construction, packageable for PyPI, and usable as the foundation for real agent applications.

## Solution

NAQSHA will ship as a Python Package published under the `naqsha` distribution, with public project name, import package, and CLI all using `naqsha`. The V1 Interface Set is the Python library plus a thin CLI. MCP, hosted service behavior, UI products, multi-agent orchestration, and heavy planners are deferred.

The Core Runtime will own the agent execution semantics. It will call a Model Client port to obtain validated NAP messages, enforce Tool Policy before executing any tool call, schedule approved tool calls through a conservative Tool Scheduler, sanitize every Untrusted Observation, persist runs as append-only JSONL QAOA Traces through a Trace Store, and write/read durable memory through a Memory Port. The default memory implementation will be a local SimpleMem-Cross Adapter, not the hosted SimpleMem MCP service.

The first implementation milestone is the Runtime Slice: deterministic local execution with a fake Model Client, NAP validation, JSONL Trace Store, Tool Policy, Tool Scheduler, Observation Sanitizer, Budget Limits, Run Profiles, and a small working subset of the Starter Tool Set. SimpleMem-Cross integration, active Reflection Loop behavior, full Starter Tool Set breadth, and PyPI release hardening follow once the Runtime Slice can replay and fail closed.

NAQSHA V1 is accepted only when it passes the Reliability Gate: deterministic replay tests, schema and policy tests, SimpleMem-Cross cross-session recall tests, and a small OWASP-mapped red-team corpus for prompt injection, unsafe tool escalation, sensitive output, and unbounded consumption.

## User Stories

1. As a Python developer, I want to install NAQSHA from PyPI, so that I can add a production-shaped agent runtime to a project without cloning a repository.
2. As a Python developer, I want to import `naqsha`, so that the installed package, CLI, and code examples use one consistent project name.
3. As a CLI user, I want to run an agent from a named Run Profile, so that model, tools, memory, budgets, traces, and approval behavior are explicit.
4. As a CLI user, I want to replay a prior run from a QAOA Trace, so that I can reproduce behavior without calling live tools again.
5. As a CLI user, I want to inspect why a tool call was allowed, denied, serialized, parallelized, or gated, so that policy behavior is understandable.
6. As a CLI user, I want high-risk tool calls to pause at an Approval Gate, so that side effects do not happen invisibly.
7. As a CLI user, I want exhausted Budget Limits to produce a structured failure, so that runaway loops are stopped predictably.
8. As a library user, I want a small Core Runtime API, so that I can embed NAQSHA without adopting a broad framework.
9. As a library user, I want the Core Runtime to depend on ports for model, memory, tracing, and tools, so that I can replace adapters without changing runtime semantics.
10. As a library user, I want to provide a fake Model Client, so that I can test agent behavior deterministically.
11. As a library user, I want the Model Client to return validated NAP messages, so that provider-specific response formats do not leak into the Core Runtime.
12. As a provider adapter author, I want to translate provider-native tool calls into NAP Actions, so that NAQSHA can support multiple model providers.
13. As a tool author, I want each tool to declare name, description, parameter schema, risk tier, and execution behavior, so that tool use is typed and policy-aware.
14. As a tool author, I want invalid parameters to fail closed before execution, so that malformed model output cannot reach side-effecting code.
15. As a tool author, I want structured tool errors to become Untrusted Observations, so that the model can recover without crashing the run.
16. As a runtime user, I want all tool output treated as Untrusted Observation, so that fetched content or command output cannot issue runtime instructions.
17. As a runtime user, I want observations sanitized before they enter traces, memory, or prompt context, so that secret-like or forbidden content is not persisted or reinjected.
18. As a security-conscious user, I want Tool Policy enforced by code, so that safety does not depend only on prompt wording.
19. As a security-conscious user, I want the Starter Tool Set allowed by default but high-risk side effects approval-gated, so that NAQSHA is useful without granting silent excessive agency.
20. As a security-conscious user, I want shell and filesystem mutation to be high-risk actions, so that destructive or sensitive operations require explicit approval.
21. As a security-conscious user, I want web content to remain delimited and untrusted, so that indirect prompt injection is not treated as authority.
22. As a security-conscious user, I want Budget Limits for steps, tokens, tool calls, wall-clock time, and per-tool execution time, so that unbounded consumption is prevented.
23. As an agent developer, I want NAP Actions to support multiple tool calls, so that independent read-only work can be represented naturally.
24. As an agent developer, I want the Tool Scheduler to run calls in parallel only when they are read-only, independent, and policy-approved, so that multi-call support does not create hidden race conditions.
25. As an agent developer, I want high-risk calls never batched past an approval boundary, so that one approval maps to a clear side effect.
26. As an agent developer, I want every run persisted as Query, Action, Observation, and Answer events, so that execution is observable.
27. As an agent developer, I want QAOA Traces stored as append-only JSONL by default, so that traces are easy to diff, replay, and inspect.
28. As an agent developer, I want provider chat transcripts to remain separate from QAOA Traces, so that replay is independent from provider internals.
29. As a privacy-conscious user, I do not want NAQSHA to require or persist private chain-of-thought, so that traces remain safer to store and share.
30. As a developer debugging a regression, I want to replay a trace with recorded observations, so that model or policy changes can be compared against a stable environment.
31. As a developer evaluating a model change, I want replay tests to verify tool selection and final answers, so that provider upgrades do not silently break behavior.
32. As a memory user, I want memory to be a first-class Memory Port, so that memory is not just prompt stuffing or chat history.
33. As a memory user, I want the default SimpleMem-Cross Adapter to persist across sessions locally, so that agents can remember prior decisions and context.
34. As a memory user, I want memory retrieval to be token-budgeted, so that useful memory competes explicitly with tool schemas and recent trace context.
35. As a memory user, I want memory writes to include provenance, so that remembered facts can be traced back to evidence.
36. As a memory user, I want SimpleMem-Cross session lifecycle events mapped cleanly from NAQSHA runs, so that memory finalization is reliable.
37. As a memory user, I want cross-session recall tested with golden scenarios, so that temporal anchoring, preference updates, contradictions, and provenance behave consistently.
38. As a developer, I want Run Profiles to configure model, tools, memory, trace location, approvals, and budgets, so that important runtime behavior is not hidden in environment variables.
39. As a developer, I want a default local Run Profile for smoke testing, so that I can verify the package without configuring a real model provider.
40. As a package maintainer, I want Hatchling and `uv` as the Packaging Baseline, so that builds are PyPI-friendly and local development is fast.
41. As a package maintainer, I want optional extras for memory, web tools, and development dependencies, so that users do not install heavy dependencies unnecessarily.
42. As a package maintainer, I want the CLI entry point named `naqsha`, so that command usage matches package naming.
43. As a package maintainer, I want package metadata, typed exports, and release checks, so that the PyPI package is credible.
44. As a package maintainer, I want deterministic test fixtures around fake models and fake tools, so that CI is stable.
45. As a package maintainer, I want no MCP dependency in V1, so that the first release remains library-and-CLI focused.
46. As a contributor, I want module boundaries that are deep and testable, so that changes to one area do not ripple across the runtime.
47. As a contributor, I want the protocol layer isolated, so that NAP and QAOA schema changes are deliberate.
48. As a contributor, I want the policy layer isolated, so that security behavior can be tested without running a real model.
49. As a contributor, I want the memory adapter isolated, so that SimpleMem-Cross can change without rewriting the Core Runtime.
50. As a contributor, I want the trace layer isolated, so that JSONL can later be swapped for SQLite or another backend.
51. As a contributor, I want reflection behavior isolated, so that active improvement features cannot mutate runtime behavior without tests and approval.
52. As a Reflection Loop user, I want failed or evaluated runs to generate reusable guidance, so that NAQSHA improves from experience.
53. As a Reflection Loop user, I want Reflection Patches created only in isolated workspaces, so that code-generating reflection cannot hotpatch the active runtime.
54. As a Reflection Loop user, I want Reflection Patches to pass the Reliability Gate before review, so that generated changes are grounded in tests.
55. As a maintainer, I want human approval before Reflection Patches merge, so that prompt injection, memory poisoning, or overfitted tests cannot expand runtime agency automatically.
56. As a maintainer, I want OWASP-mapped red-team tests, so that safety claims are tied to a recognized risk taxonomy.
57. As a maintainer, I want NIST AI RMF and Generative AI Profile alignment documented as guidance, so that future production deployments have a governance spine.
58. As a future adapter author, I want MCP deferred rather than embedded in the Core Runtime, so that MCP can later be added without changing core semantics.
59. As a future product builder, I want hosted service behavior out of V1, so that NAQSHA can stabilize as a runtime before becoming a platform.
60. As a future planner author, I want heavy planners and multi-agent orchestration out of V1 core, so that they can be optional outer layers around a stable runtime.

## Implementation Decisions

- Build NAQSHA as a Python Package with public project name, import package, CLI command, and PyPI distribution all named `naqsha`.
- Use a Packaging Baseline based on `pyproject.toml`, Hatchling, `uv`, package metadata, typed exports, console script `naqsha`, and optional extras for memory, web tools, and development dependencies.
- Keep the V1 Interface Set to the Python library and CLI. MCP adapters, hosted services, and UI products are out of V1.
- Center implementation around the Core Runtime as the deepest module. It should expose a compact execution interface and delegate provider calls, memory, tracing, tools, policy, approvals, and configuration to explicit ports or adapters.
- Build the Runtime Slice first. It includes deterministic fake-model execution, NAP validation, QAOA JSONL tracing, Tool Policy, Tool Scheduler, Observation Sanitizer, Budget Limits, Run Profiles, and a small subset of the Starter Tool Set.
- Define the Model Client port as the only model-facing dependency of the Core Runtime. Provider adapters convert provider-native formats into validated NAP messages.
- Define NAP Action as the strict model-facing action protocol. It supports final answers and one or more tool calls, but does not require or persist private chain-of-thought.
- Define QAOA Trace as the canonical persisted run model. It records Query, Action, Observation, and Answer events, independent of provider chat transcript formats.
- Use append-only JSONL as the default Trace Store in V1. Keep the Trace Store interface replaceable so SQLite, Postgres, or object storage can come later.
- Implement deterministic replay over QAOA Traces. Replay should use recorded observations and deterministic fake model outputs where appropriate.
- Define tools with schema, description, risk tier, and execution behavior. Tool schemas are validated before execution.
- Ship the research-inspired Starter Tool Set in V1: web search, web fetch, calculator, clock, read file, write file, run shell, JSON patch, and human approval.
- Allow the Starter Tool Set by default, but require Approval Gates for high-risk side effects such as shell execution, filesystem mutation, destructive JSON patching, or policy-sensitive actions.
- Implement Tool Policy as runtime enforcement, not prompt guidance. Tool Policy decides allowed tools, risk tiers, approval requirements, and denial behavior.
- Implement Approval Gate as a blocking pre-execution checkpoint with human or callback approval. It is not merely audit logging.
- Implement Budget Limits as hard caps for max steps, model tokens, tool calls, wall-clock time, and per-tool execution time. Exhaustion fails closed with structured trace events.
- Implement Tool Scheduler conservatively. Multiple calls in one NAP Action may run in parallel only when read-only, independent, and policy-approved; all other calls run serially.
- Treat every tool output as an Untrusted Observation. Observation text can inform the model but cannot instruct the runtime.
- Run Observation Sanitizer before persistence to traces, memory writes, or prompt reinjection. It should redact secret-like values and block or mark policy-forbidden content.
- Define Run Profiles as named runtime configuration objects. They select model adapter, tools, memory behavior, trace location, budgets, approval behavior, and sanitizer settings.
- Define Memory Port as a first-class Core Runtime contract. Memory is not chat history and not an implicit prompt appendix.
- Ship a local SimpleMem-Cross Adapter as the default Memory Port implementation. The hosted SimpleMem MCP service is not the default and MCP is deferred from V1.
- Map NAQSHA run lifecycle to SimpleMem-Cross session lifecycle. Start sessions with user context, record messages and tool outcomes, stop sessions to extract observations, and close resources cleanly.
- Keep memory retrieval token-budgeted. Retrieved memory should enter the model context as delimited, provenance-aware memory summaries.
- Keep memory write paths sanitized. Untrusted Observations must not bypass the Observation Sanitizer before memory persistence.
- Include active-by-default Reflection Loop behavior in V1, but constrain code changes to Reflection Patches in isolated workspaces.
- Require Reflection Patches to pass the Reliability Gate before human review.
- Prohibit runtime hotpatching and automatic merging of Reflection Patches. Human approval is required before generated code changes affect the active runtime.
- Keep Reflection Loop behavior behind explicit module boundaries so it cannot silently modify Tool Policy, approval behavior, model provider config, or active code.
- Use the Reliability Gate as the V1 acceptance bar, not a demo. The release is incomplete until replay, policy, memory, and OWASP-mapped red-team tests pass.
- Use OWASP LLM Top 10 2025 as the safety taxonomy for prompt injection, sensitive information disclosure, improper output handling, excessive agency, vector and embedding weaknesses, misinformation, and unbounded consumption.
- Use NIST AI RMF and NIST-AI-600-1 as non-binding governance guidance for future production deployments, not as a V1 compliance claim.
- Keep heavy planners, tree search, paradigm routing, multi-agent orchestration, hosted services, multimodal memory, and MCP adapters out of V1 core.

## Testing Decisions

- Good tests should exercise externally visible behavior: accepted and rejected NAP messages, persisted QAOA Trace events, Tool Policy decisions, approval pauses, sanitized observations, replay results, memory recall outcomes, and CLI behavior.
- Tests should not assert incidental implementation details such as private helper call order, internal object layout, or exact prompt string formatting except where prompt blocks are part of a public contract.
- The Core Runtime should have deterministic tests with fake Model Clients, fake tools, fake approvals, and temporary Trace Stores.
- The NAP protocol module should be tested with valid action messages, valid final messages, malformed JSON, schema-invalid calls, unknown tools, duplicate call IDs, missing parameters, unexpected fields, and chain-of-thought-like fields that must not be required.
- The QAOA Trace module should be tested for append-only writes, event ordering, replay loading, corrupted line handling, schema evolution behavior, and redaction boundaries.
- The Tool Policy module should be tested for allowed tools, denied tools, risk-tier enforcement, approval-required calls, approval-denied calls, and policy explanations.
- The Tool Scheduler should be tested for serial execution, safe parallel execution, denial of unsafe batching, preservation of observation ordering, and failure behavior when one call in a batch fails.
- The Observation Sanitizer should be tested with secret-like strings, prompt injection strings, overly large outputs, binary-like content, structured tool errors, and safe ordinary output.
- The Budget Limit behavior should be tested for max steps, max tool calls, per-tool timeout, wall-clock timeout, token budget exhaustion where measurable, and best-partial-answer behavior.
- The Run Profile loader should be tested for valid profiles, missing required fields, invalid tools, invalid budgets, invalid memory configuration, and explicit defaulting behavior.
- The CLI should be tested through command-level behavior: running a profile, replaying a trace, inspecting policy decisions, approving or denying high-risk calls, and reporting structured failures.
- The Memory Port should be tested with an in-memory fake implementation before SimpleMem-Cross integration, so Core Runtime memory semantics are stable.
- The SimpleMem-Cross Adapter should be tested for session start, event recording, tool-use recording, stop/finalize behavior, context retrieval, provenance preservation, cleanup, and error handling.
- Memory regression tests should include temporal anchoring, latest-preference-wins behavior, contradiction handling, provenance references, cross-session recall, and irrelevant memory suppression.
- Reflection Loop tests should verify candidate generation, Reliability Gate execution, isolated Reflection Patch creation, rejection of runtime hotpatching, and human approval requirement.
- OWASP-mapped red-team tests should include indirect prompt injection through web content, tool output containing secret-like strings, attempts to escalate from web/fetch to shell, malicious memory content, oversized outputs, and loop-inducing model behavior.
- Packaging tests should verify package metadata, import name, CLI entry point, optional extras, sdist/wheel build, and installation in a clean environment.
- Release smoke tests should verify that a fresh installation can run the local fake-model Runtime Slice without external API keys.
- Prior art in this repo is limited to the glossary and ADRs; there is no existing implementation test suite to mirror. The first test layout should therefore be designed around the module boundaries above.

## Out of Scope

- Publishing under the `naqsh` PyPI name.
- Supporting MCP in V1, including both MCP client and MCP server adapters.
- Using the hosted SimpleMem MCP service as the default memory backend.
- Building a hosted NAQSHA service, web UI, dashboard, or multi-tenant platform.
- Implementing heavy planners, tree search, paradigm routing, or multi-agent orchestration in V1 core.
- Supporting multimodal memory through Omni-SimpleMem in V1.
- Persisting private chain-of-thought as part of QAOA Trace.
- Treating provider-native chat transcripts as the canonical trace model.
- Making shell or filesystem mutation silently executable without Approval Gates.
- Allowing Reflection Patches to hotpatch the active runtime or merge without human approval.
- Claiming formal compliance with OWASP, NIST, or other governance frameworks.
- Optimizing for a hard Core Runtime line-count target.
- Building TypeScript, Rust, Go, or other SDKs in parallel with the Python package.

## Further Notes

The original research used the name NAQSH, but the public project name is now NAQSHA because `naqsh` is already occupied on PyPI. The research also suggested MCP as a deployment option; V1 deliberately defers MCP so the Python library and CLI can stabilize first.

The most important deep modules are the Core Runtime, NAP/QAOA protocol layer, Tool Policy and Tool Scheduler, Trace Store, Memory Port with SimpleMem-Cross Adapter, Observation Sanitizer, Run Profile configuration, and Reflection Loop. These modules should be kept independently testable, with narrow interfaces and broad internal responsibility.

This PRD could not be published to an issue tracker from the current workspace because the directory is not a git repository and no remote issue tracker metadata is available. When an issue tracker is available, publish this PRD as a new issue and apply the `needs-triage` label.

# Red-team corpus ↔ OWASP LLM Top 10 (informative)

This document maps NAQSHA regression tests to **OWASP LLM Top 10
(2025 / 1.1)** categories. It is **not** a claim of formal OWASP or NIST
compliance—only an engineering traceability aid.

| OWASP ID | Theme | NAQSHA coverage |
|---------|--------|-----------------|
| LLM01 Prompt Injection | Indirect prompt injection via untrusted content | `tests/test_sanitizer.py` (baseline: non-secret injection strings pass through sanitizer); `tests/redteam/test_corpus.py::test_llm03_memory_poisoning_is_wrapped_untrusted` (memory wrapped as untrusted evidence). |
| LLM02 Insecure Output Handling | Downstream systems trust model/tool output | Boundary is **Untrusted Observation** + sanitizer before trace/memory/prompt; see `tests/test_policy_and_trace.py::test_trace_file_observations_are_post_sanitizer`. |
| LLM03 Training Data Poisoning | Poisoned retrieval / memory | `tests/redteam/test_corpus.py::test_llm03_memory_poisoning_is_wrapped_untrusted`; `tests/test_memory_simplemem_cross.py` (recall + suppression). |
| LLM04 Model Denial of Service | Resource exhaustion, loops | `tests/redteam/test_corpus.py::test_llm04_loop_inducing_model_stopped_by_budget`; `tests/test_guardrails.py` (budgets, per-tool timeouts). |
| LLM05 Supply Chain Vulnerabilities | Third-party models, packages | Out of scope for automated red-team in this repo; handled operationally (pinned deps, supply-chain review). |
| LLM06 Sensitive Information Disclosure | Leaks via model, tools, logs | `tests/test_sanitizer.py` (secret-like redaction); `tests/test_policy_and_trace.py` (post-sanitizer trace persistence). |
| LLM07 Insecure Plugin Design | Unsafe or overly powerful tools | Starter Tool Set risk tiers + **Tool Policy** + **Approval Gate**: `tests/test_guardrails.py`, `tests/test_starter_tools.py`, `tests/redteam/test_corpus.py::test_llm07_tool_escalation_unknown_tool_denied`. |
| LLM08 Excessive Agency | Unintended actions / scope creep | Policy allowlists and approval tiers: `tests/test_guardrails.py`; unknown tools denied (red-team). |
| LLM09 Overreliance | Humans trust wrong outputs | Product/process concern; tests focus on traceability (`tests/test_trace_replay.py`, CLI `replay --re-execute`). |
| LLM10 Model Theft | Model exfiltration | Not mapped in this corpus; operational controls only. |

## Related artifacts

- **Replay / evaluation:** `tests/test_trace_replay.py`, `naqsha replay --re-execute`.
- **Trace integrity:** `tests/test_policy_and_trace.py`.

# NAQSHA V1 Development Handoff

This document is the phase plan for building NAQSHA v1 through separate chat
sessions. Start a new chat for each phase. Each chat should finish one coherent
slice, update this document if reality changes, and update `AGENTS.md` when it
learns a rule future agents need.

## How To Run Each Phase

At the start of every new chat, give the agent this instruction:

```text
Read CONTEXT.md, AGENTS.md, docs/prd/0001-naqsha-v1-runtime.md, all docs/adr/*.md,
and docs/handoff/0001-v1-development-workflow.md. Work only on Phase <N>. Preserve
the vocabulary and module boundaries. Add or update tests first where useful. When
done, update AGENTS.md with any new durable guidance and update the handoff phase
status if needed.
```

Every phase should end with:

- `uv run --extra dev pytest`
- `uv run --extra dev ruff check .`
- a short note in the final response listing what changed, what remains, and any
  risk the next phase inherits

Do not combine phases unless the earlier phase is already complete and verified.
The phases are sliced around stable contracts so a weaker agent can keep context
small and still produce useful work.

## Phase 0: Scaffold Baseline

Status: complete.

Purpose: establish the package, module boundaries, CLI smoke path, deterministic
fake-model runtime, and first tests.

Already delivered:

- `pyproject.toml` with Hatchling, `uv`, dev extras, console script, Ruff, Pytest
- `README.md` and `AGENTS.md`
- `src/naqsha/` package with Core Runtime, NAP/QAOA protocols, JSONL trace store,
  Tool Policy, Approval Gate, budgets, scheduler, sanitizer, starter tools,
  memory/model ports, replay helper, and Reflection Loop boundary
- deterministic tests for NAP validation, policy, trace store, runtime execution,
  approval denial, and sanitized memory recording

Exit result:

- local fake-model CLI can run with no API keys
- tests and Ruff pass
- future phases can extend ports/adapters without moving Core Runtime semantics

## Phase 1: Protocol And Trace Hardening

Status: complete.

Goal: make NAP and QAOA strong enough that later model, replay, and adapter work
cannot accidentally change public runtime semantics.

Delivered:

- Stricter NAP parsing: non-object payloads, string `kind`, unknown kinds,
  malformed `calls`, duplicate IDs, oversize IDs, forbidden/control characters,
  leading/trailing whitespace in IDs, non-string / empty argument keys,
  chain-of-thought-like extra fields at action and call level.
- Unknown tool names remain a **Tool Policy** decision (`policy.py`), with an
  explicit regression test at the policy boundary.
- QAOA Trace records carry integer `schema_version` (`QAOA_TRACE_SCHEMA_VERSION`);
  lines without it load as version 1; unsupported versions fail closed.
- `TraceEvent.from_dict` validates top-level keys, kinds, and payload shapes per
  kind; raises `TraceValidationError` for structural violations.
- JSONL load wraps decode and validation failures as `ValueError` with line numbers.
- Protocol tests cover NAP and QAOA contracts; trace tests cover ordering, invalid
  lines, replay summaries, and post-sanitizer persistence (redaction boundary).
- V1 stays **dataclass + explicit validation** in `protocols/` (no new validation
  dependency); evolution strategy documented in `protocols/qaoa.py` module docstring.

Expected result (met):

- Protocol tests explain the stable NAP and QAOA contracts.
- Trace persistence failures are structured and debuggable.
- Future model adapters can only enter the Core Runtime through validated NAP
  messages.

Do not:

- Add provider-native chat transcripts to QAOA Trace.
- Store private chain-of-thought.
- Put tool execution or policy logic into `protocols/`.

## Phase 2: Run Profiles And CLI Usability

Status: complete.

Goal: make local execution explicit through named Run Profiles instead of hidden
defaults or one-off CLI wiring.

Delivered:

- Profile loader (`load_run_profile`, `parse_run_profile`) for `.json` and `.toml`
  into validated `RunProfile` (`profiles.py`): model kind, Starter Tool subset
  allowlist, paths (resolved relative to the profile file directory), trace and
  tool root, budgets, approval tiers / auto approve, Memory Port adapter (`none`,
  `inmemory`; `simplemem_cross` deferred with a clear validation error), Observation
  Sanitizer `max_chars`, optional scripted fake-model NAP messages (each validated via
  NAP parsing).
- CLI `--profile PATH_OR_NAME` for `run`, `replay`, and `inspect-policy` (default name
  `local-fake` resolves to bundled profile); overrides `--trace-dir`, `--tool-root`,
  `--auto-approve`; profile errors exit `2` with stderr message.
- Bundled smoke profile `src/naqsha/bundled_profiles/local-fake.json` and mirrored
  example copy under `examples/profiles/` with short README.
- Command-level tests: `tests/test_cli.py`, `tests/test_profiles.py`.

Expected result (met):

- A user can run `naqsha run --profile <profile> "query"` with explicit runtime
  choices.
- Profile validation errors are clear.
- CLI behavior is covered by tests and does not require external API keys.

Do not:

- Hide important runtime behavior in environment variables only.
- Add live provider setup in this phase except as a documented placeholder.

## Phase 3: Policy, Approval, Scheduler, And Budgets

Status: complete.

Goal: make fail-closed runtime guardrails broad and testable before adding more
powerful tools.

Delivered:

- Expanded Tool Policy tests: allowlist deny, write-tier approval requirement,
  gate denial, readable reasons; trace validation for optional action `scheduler`
  metadata (`mode` serial|parallel, `parallel_eligible`).
- CLI `--approve-prompt` wires `InteractiveApprovalGate` (stdin y/yes per call);
  profile `auto_approve` and `--auto-approve` still override.
- `BudgetMeter.check_wall_clock()` for explicit wall-clock checks; scheduler invokes
  wall-clock checks between tool waits; `consume_step` / `consume_tool_call` unchanged.
- Per-tool timeouts via `ThreadPoolExecutor.result(timeout=...)` in `ToolScheduler`;
  unsafe batches stay serial (duplicate tool names or any non-read-only tool).
- Safe parallel execution for distinct read-only tools; observations persisted in
  call order.
- Documented multi-call behavior: a failing tool yields a failed observation; later
  calls in the same NAP Action still run.
- Budget tests: max steps, max tool calls, wall-clock path, per-tool timeout,
  partial answer semantics (`RunResult.answer` None when run fails before answer).

Expected result (met):

- High-risk tools cannot execute silently without approval configuration.
- Budget exhaustion creates structured QAOA failure events.
- Scheduler behavior is visible in tests and in trace action `scheduler` metadata.

Do not:

- Let one approval cover multiple high-risk side effects unless the trace makes
  that explicit and tests prove the intended behavior.
- Treat budgets as warnings.

## Phase 4: Starter Tool Set Completion

Status: complete.

Goal: replace placeholders with useful, policy-aware starter tools while keeping
all tool output as Untrusted Observation.

Delivered:

- `web_fetch`: stdlib `urllib` only; `http`/`https` only; delimited **Untrusted Observation**
  envelopes; response body size caps and fetch timeouts; structured HTTP errors.
- `web_search`: DuckDuckGo Instant Answer API via stdlib (dependency-light); delimited
  untrusted text; optional `[web]` extra in `pyproject.toml` reserved for heavier backends.
- `run_shell`: `argv` list only (`shell=False`); `cwd` constrained under tool root;
  timeout capped; `RiskTier.HIGH`; exit code and stdout/stderr as structured observations.
- `read_file` / `write_file`: root boundary checks; binary and non-UTF-8 refusal;
  optional `max_bytes` on read; `overwrite` flag on write (default false).
- `json_patch`: RFC 6902 subset (`add`, `remove`, `replace`, `test`); parse and validate
  operations before any write; atomic replace via temp file; `RiskTier.WRITE`.
- `human_approval`: clarifies that real gating is the **Approval Gate** (read-only tool).
- `calculator` / `clock` unchanged; tests use `sys.executable` for subprocess portability.
- `tests/test_starter_tools.py`: schema/success/error/sanitizer/policy coverage;
  `tests/test_runtime.py` updated for `run_shell` argv.
- `validate_arguments` extended for `integer` and `array` item types.

Expected result (met):

- The Starter Tool Set from the PRD exists as real tools.
- Tool metadata is accurate and policy-aware.
- Unsafe tool use fails closed before side effects.

Do not:

- Let web content, file content, or shell output issue runtime instructions.
- Execute shell or filesystem mutation without Approval Gate enforcement.

## Phase 5: Memory Port And SimpleMem-Cross Adapter

Goal: make durable memory a first-class runtime feature while keeping
SimpleMem-Cross behind an adapter boundary.

Work to do:

- Strengthen Memory Port tests with the in-memory fake before touching
  SimpleMem-Cross.
- Implement SimpleMem-Cross adapter session start, event recording, tool-use
  recording, stop/finalize behavior, context retrieval, provenance preservation,
  cleanup, and error handling.
- Map NAQSHA run lifecycle cleanly to SimpleMem-Cross session lifecycle.
- Ensure retrieved memory is token-budgeted, delimited, provenance-aware, and
  not treated as instructions.
- Ensure memory writes only receive sanitized observations.
- Add golden memory scenarios for temporal anchoring, latest-preference-wins,
  contradiction handling, provenance references, cross-session recall, and
  irrelevant memory suppression.

Expected result:

- Core Runtime memory semantics are stable with fake memory and SimpleMem-Cross.
- Cross-session recall works locally.
- Memory integration does not leak SimpleMem-Cross internals into Core Runtime.

Do not:

- Use hosted SimpleMem MCP as the default.
- Add MCP dependencies to the Core Runtime.
- Treat memory as chat history or implicit prompt stuffing.

## Phase 6: Model Provider Adapter

Goal: add one real model adapter without changing Core Runtime semantics.

Work to do:

- Add an OpenAI-compatible or similarly simple provider adapter under
  `src/naqsha/models/`.
- Translate provider-native output into validated NAP messages before returning
  from `ModelClient`.
- Keep credentials out of traces and tests.
- Add provider adapter tests with mocked HTTP/client responses.
- Add examples showing how to configure the adapter through Run Profiles.
- Preserve fake model tests as the default deterministic path.

Expected result:

- NAQSHA can run with a real model through a profile.
- Provider-specific formats do not leak into `runtime.py`, QAOA Trace, tools, or
  policy.
- CI remains stable without live network or API keys.

Do not:

- Make a live provider the default test path.
- Persist provider-native chat transcripts as canonical traces.

## Phase 7: Replay, Evaluation, And Red-Team Gate

Goal: turn the Reliability Gate into a concrete test suite rather than a promise.

Work to do:

- Implement deterministic replay that can use recorded observations without
  calling live tools again.
- Add replay tests for tool selection and final-answer comparison.
- Add OWASP-mapped red-team fixtures for indirect prompt injection, unsafe tool
  escalation, sensitive output, malicious memory content, oversized outputs, and
  loop-inducing model behavior.
- Add sanitizer tests for secret-like strings, prompt injection strings, large
  outputs, binary-like content, structured tool errors, and safe ordinary output.
- Add documentation mapping the red-team corpus to OWASP LLM Top 10 categories.

Expected result:

- Replay catches behavior regressions.
- Safety claims are backed by executable tests.
- Sanitizer and policy boundaries are visible in traces.

Do not:

- Claim formal OWASP or NIST compliance.
- Let red-team fixtures depend on external services.

## Phase 8: Reflection Loop Boundary

Goal: implement active reflection without giving it authority to mutate the
active runtime.

Work to do:

- Implement candidate reflection generation from evaluated runs.
- Create isolated Reflection Patch workspaces.
- Require the Reliability Gate to pass before a Reflection Patch is marked ready
  for human review.
- Add tests proving reflection cannot hotpatch active code, modify Tool Policy,
  bypass approvals, or merge automatically.
- Document the review workflow for Reflection Patches.

Expected result:

- Reflection can propose improvements.
- Human review remains mandatory before changes affect the active runtime.
- Prompt injection, memory poisoning, and overfit replay tests cannot silently
  expand runtime agency.

Do not:

- Auto-merge Reflection Patches.
- Let reflection edit active runtime files in place.

## Phase 9: Packaging And Release Hardening

Goal: make NAQSHA credible as the `naqsha` Python Package.

Work to do:

- Verify package metadata, import name, typed exports, license metadata, README,
  optional extras, console script, sdist, and wheel.
- Add clean-environment installation tests.
- Add release smoke tests that run the local fake-model Runtime Slice without
  external API keys.
- Add CI configuration if this workspace becomes a git repo.
- Document PyPI release checklist and versioning expectations.

Expected result:

- `naqsha` can be built, installed, imported, and run from a clean environment.
- Release checks prove the local fake-model path works.
- Optional extras remain optional.

Do not:

- Publish under `naqsh`.
- Add hosted service, UI, MCP, or multi-agent orchestration to v1 release scope.

## Phase 10: V1 Acceptance Review

Goal: decide whether v1 meets the PRD's Reliability Gate.

Work to do:

- Run the full test suite, Ruff, packaging checks, replay tests, memory tests, and
  red-team tests.
- Review every ADR against implementation behavior.
- Review `CONTEXT.md` flagged ambiguities and mark any newly resolved ambiguity in
  docs or ADRs.
- Check that `README.md`, `AGENTS.md`, examples, and this handoff document match
  the real code.
- Produce a short v1 acceptance report under `docs/release/`.

Expected result:

- The project has a clear yes/no answer for v1 readiness.
- Any remaining gaps are documented as explicit post-v1 work or blockers.
- Future work can start from a stable baseline.

Do not:

- Accept v1 based only on a demo.
- Ignore failing red-team, replay, memory, or packaging checks.

## AGENTS.md Update Rule

Every phase must consider whether `AGENTS.md` needs an update. Update it when a
phase creates durable guidance about:

- module boundaries
- public contracts
- testing commands or fixtures
- safety rules
- dependency choices
- adapter patterns
- known traps future agents are likely to repeat

Do not add noisy implementation history to `AGENTS.md`. Keep this handoff document
for phase state and project sequencing; keep `AGENTS.md` for standing instructions
that should remain true across phases.

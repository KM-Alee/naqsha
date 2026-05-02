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

Status: complete.

Goal: make durable memory a first-class runtime feature while keeping
SimpleMem-Cross behind an adapter boundary.

Delivered:

- Strengthened in-memory Memory Port coverage (`tests/test_memory_port.py`: ok-only
  recording, char-budgeted `retrieve` aligned with `~4` chars per token).
- **SimpleMem-Cross-style** adapter (`memory/simplemem_cross.py`): stdlib SQLite + WAL;
  maps `start_run` / `record_observation` / `finish_run` to durable rows; `retrieve`
  ranks by keyword hits (token-boundary safe) and recency, wraps evidence in explicit
  **untrusted** delimiters with provenance metadata; sanitized observations only reach
  the store via Core Runtime unchanged.
  PyPI `simplemem` ships the embedding-heavy base package without the repository's
  unpublished `cross/` façade; NAQSHA implements the lifecycle contract locally
  without Torch/Lance/pyarrow dependencies.
- Run Profile keys `memory_cross_project` (default `default`), `memory_cross_database`
  (default `.naqsha/simplemem-cross.sqlite` resolved like other paths).
- CLI `simplemem_cross` wires the adapter (`cli.build_runtime`).
- Golden tests: cross-session calculator recall, irrelevant suppression,
  latest-preference ordering, provenance echoes, malformed observation guard
  (`tests/test_memory_simplemem_cross.py`); hyphen-normalized adapter name parsing.
- Example profile `examples/profiles/simplemem-cross-fake.json`.

Expected result (met):

- Core Runtime memory semantics are stable with fake memory and SQLite Cross-style storage.
- Cross-session recall works locally.
- Memory integration does not leak storage internals into `CoreRuntime` (port-only surface).

Do not:

- Use hosted SimpleMem MCP as the default.
- Add MCP dependencies to the Core Runtime.
- Treat memory as chat history or implicit prompt stuffing.

## Phase 6: Model Provider Adapter

Status: complete.

Goal: add one real model adapter without changing Core Runtime semantics.

Delivered:

- Shared adapter plumbing (stdlib HTTP): `models/trace_turns.py` rebuilds a neutral
  **conversation transcript** from QAOA trace + Memory Port text (single source of truth for
  multi-turn tool loops); `models/http_json.py` centralizes JSON POST, HTTP error parsing
  (including Anthropic `type: error` envelopes), and header redaction; `models/errors.py` defines
  `ModelInvocationError`; `models/factory.py` implements `model_client_from_profile` wired from
  `cli.build_runtime`.
- OpenAI-compatible Chat Completions (`models/openai_compat.py`): POST
  `{base_url}/chat/completions`; `tool_calls` / assistant text → NAP.
- Anthropic Claude Messages API (`models/anthropic.py`): POST `{base_url}/v1/messages`;
  `tool_use` / text blocks → NAP; headers `x-api-key`, `anthropic-version`.
- Google Gemini `generateContent` (`models/gemini.py`): POST
  `{base_url}/v1beta/models/{model}:generateContent`; `functionCall` / text parts → NAP;
  header `x-goog-api-key`; `functionResponse` replays include tool name + optional call id.
- Run Profile `model` ∈ `fake`, `openai_compat`, `anthropic`, `gemini` with matching nested
  sections (`openai_compat`, `anthropic`, `gemini`); only env-var **names** for secrets;
  `fake_model` rejected for all remote adapters.
- Examples: `openai-compat.example.json`, `anthropic.example.json`, `gemini.example.json`;
  tests in `tests/test_openai_compat_model.py`, `tests/test_anthropic_model.py`,
  `tests/test_gemini_model.py`, `tests/test_trace_turns.py`, and profile tests.

Expected result (met):

- NAQSHA can run with a real model through a profile.
- Provider-specific formats do not leak into `runtime.py`, QAOA Trace, tools, or
  policy.
- CI remains stable without live network or API keys.

Do not:

- Make a live provider the default test path.
- Persist provider-native chat transcripts as canonical traces.

## Phase 7: Replay, Evaluation, And Red-Team Gate

Status: complete.

Goal: turn the Reliability Gate into a concrete test suite rather than a promise.

Delivered:

- **Trace replay execution**: `TraceReplayModelClient` replays the NAP Action/Answer sequence
  from a reference QAOA trace; `ToolScheduler(recorded_observations=...)` returns persisted
  observations by **call id** (no live tool execution for approved calls). Helpers in
  `replay.py` (`nap_messages_from_trace`, `observations_by_call_id`, `compare_replay`,
  `tool_calls_chronology`). `ToolObservation.from_trace_payload` rebuilds observations from JSON.
- **CLI**: `naqsha replay RUN_ID` (JSON summary, or `--human` text); `naqsha replay RUN_ID
  --re-execute` runs a second pass and prints comparison fields; exit `1` when the new run fails
  or diverges on answer or tool-call path from the reference trace; `--approve-prompt` supported
  for replay parity.
- **Evaluation tests**: `tests/test_trace_replay.py` (round-trip, diff, scheduler missing obs);
  `tests/test_cli.py` (`--re-execute` smoke).
- **Red-team corpus**: `tests/redteam/test_corpus.py` (memory poisoning wrapper, unknown-tool
  denial, loop/budget); mapping doc `docs/redteam/owasp-llm-top10-mapping.md` (informative, not a
  compliance claim).
- **Sanitizer tests**: `tests/test_sanitizer.py` (secrets, truncation, injection-string baseline,
  structured errors, binary-like text).

Expected result (met):

- Replay catches behavior regressions (answer + tool path).
- Safety claims are backed by executable tests.
- Sanitizer and policy boundaries remain visible in traces and tests.

Do not:

- Claim formal OWASP or NIST compliance.
- Let red-team fixtures depend on external services.

## Phase 8: Reflection Loop Boundary

Status: complete.

Goal: implement active reflection without giving it authority to mutate the
active runtime.

Delivered:

- **Reliability Gate** (`reflection/reliability_gate.py`): subprocess `pytest` over a fixed
  file list (replay, protocols, policy+trace, SimpleMem-Cross, red-team corpus);
  `resolve_project_root_for_gate()` discovers a checkout; missing `tests/` fails closed.
- **Isolated workspaces** (`reflection/workspace.py`): `create_isolated_workspace` rejects
  paths under the installed `naqsha` package directory.
- **Candidate artifacts** (`reflection/candidate.py`): deterministic `CANDIDATE.md` and
  `meta.json` from trace facts (plus `READY_FOR_REVIEW.txt` / `GATE_FAILED.txt`).
- **`SimpleReflectionLoop`** (`reflection/loop.py`): injectable `gate_runner`; library
  test hooks `noop_gate_runner` / `failing_gate_runner`; no imports of Core Runtime,
  Tool Policy, or Approval Gate.
- **`ReflectionPatch`** (`reflection/base.py`): `ready_for_human_review` mirrors gate pass;
  no merge/apply API.
- **CLI**: `naqsha reflect RUN_ID` with `--workspace-base` (default
  `.naqsha/reflection-workspaces` under cwd).
- **Documentation**: `docs/reflection-patch-review.md` (human review workflow).
- **Tests**: `tests/test_reflection_loop.py` (workspace isolation, gate pass/fail,
  forbidden imports in `reflection/*.py`, CLI smoke with fast gate).

Expected result (met):

- Reflection can propose improvements as on-disk artifacts.
- Human review remains mandatory before changes affect the active runtime.
- Prompt injection, memory poisoning, and overfit replay tests cannot silently
  expand runtime agency via this module (no policy/runtime binding; no auto-merge).

Do not:

- Auto-merge Reflection Patches.
- Let reflection edit active runtime files in place.

## Phase 9: Packaging And Release Hardening

Status: complete.

Goal: make NAQSHA credible as the `naqsha` Python package.

Delivered:

- **License and metadata**: root `LICENSE` (MIT); `pyproject.toml` `[project.urls]` (homepage,
  repository, issues); `[tool.hatch.build.targets.sdist]` includes `LICENSE`, `README.md`,
  `pyproject.toml`, and `src/`.
- **Dev tooling**: `build` added to the `dev` extra for local and CI `python -m build` parity.
- **Install tests** (`tests/test_packaging_install.py`): one module-scoped wheel+sdist build;
  wheel lists `naqsha/py.typed`; isolated venvs install the wheel and (with preinstalled
  `hatchling`) the sdist via `--no-build-isolation`, then run `naqsha run --profile local-fake`
  without API keys.
- **CI** (`.github/workflows/ci.yml`): `uv sync --extra dev`, Ruff, full pytest on Python
  3.11 and 3.12.
- **Release docs**: `docs/release/pypi-checklist.md` (versioning, `twine check`, upload,
  post-release smoke).
- **README** aligned with shipped adapters, tools, and recommended `uv run --extra dev` commands.

Expected result (met):

- `naqsha` can be built, installed, imported, and run from a clean environment.
- Release checks include the local fake-model path (packaging tests + checklist).
- Optional extras remain optional (`memory`, `web` placeholders).

Do not:

- Publish under `naqsh`.
- Add hosted service, UI, MCP, or multi-agent orchestration to v1 release scope.

### Risks the next phase inherits

- Packaging tests add ~tens of seconds (wheel+sdist build once per test module).
- **Phase 8 note still applies**: default `naqsha reflect` runs a nested full pytest over the
  Reliability Gate paths; wheel-only installs without a checkout keep `ready_for_human_review`
  false until `project_root` is a dev tree or tests inject `noop_gate_runner` (see
  `docs/reflection-patch-review.md`).

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

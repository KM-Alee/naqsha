# Agent Development Guide

Read these files first, in order:

1. `CONTEXT.md`
2. `docs/prd/0001-naqsha-v1-runtime.md`
3. all ADRs in `docs/adr/`
4. `docs/handoff/0001-v1-development-workflow.md`
5. this file
6. `README.md`

## Non-Negotiable Vocabulary

Use the glossary in `CONTEXT.md`. In particular:

- Say **NAQSHA**, not NAQSH.
- Say **Core Runtime**, not platform or app.
- Say **QAOA Trace**, not provider transcript or debug log.
- Say **NAP Action**, not free-form model instruction.
- Say **Memory Port**, not chat history.
- Say **Tool Policy** and **Approval Gate**, not prompt-only safety.

## Module Ownership

Future agents should keep these boundaries intact:

- `runtime.py` orchestrates a run and owns execution semantics.
- `protocols/` owns stable public protocol schemas. **QAOA Trace** JSONL rows include
  `schema_version`; bump `QAOA_TRACE_SCHEMA_VERSION` and `_SUPPORTED_SCHEMA_VERSIONS`
  in `protocols/qaoa.py` when evolving persisted trace shape. Omitted `schema_version`
  on disk is treated as version `1`.
- `trace/` owns persistence and replay loading, not model behavior.
- `policy.py` decides allow, deny, and approval requirements.
- `approvals.py` defines Approval Gate implementations (`StaticApprovalGate` for tests,
  `InteractiveApprovalGate` for CLI `--approve-prompt`).
- `scheduler.py` decides serial versus parallel execution after policy approval;
  records scheduling metadata on trace `action` events (`scheduler.mode`,
  `scheduler.parallel_eligible`). Enforces per-tool timeouts when a `BudgetMeter`
  is supplied. Optional `ToolScheduler(recorded_observations=...)` replays persisted
  **Untrusted Observation** payloads by **call id** (no live tool I/O) for approved calls.
- `tools/` defines executable capabilities and risk metadata. The **Starter Tool Set**
  lives in `tools/starter.py` with stdlib HTTP in `tools/http_utils.py` and JSON Patch
  helpers in `tools/json_patch.py`.
- `memory/` adapts durable memory behind the Memory Port. The **SimpleMem-Cross Adapter**
  (`memory/simplemem_cross.py`) lives here: SQLite + Cross-style lifecycle, no MCP. PyPI package
  `simplemem` is the unrelated embedding-heavy base library and does **not** include the
  repository-only `cross/` facade—do not conflate them when adding dependencies.
- `models/` adapts provider output into validated NAP messages (stdlib HTTP only). Shared
  modules: `models/trace_turns.py` (QAOA trace → neutral transcript for all providers),
  `models/http_json.py` (JSON POST + structured HTTP errors + header redaction),
  `models/errors.py` (`ModelInvocationError`). `models/trace_replay.py` is the
  `TraceReplayModelClient` (replay NAP sequence from a reference trace). Remote clients:
  `openai_compat.py` (Chat Completions), `anthropic.py` (Claude Messages API),
  `gemini.py` (`generateContent`). `models/factory.py` provides `model_client_from_profile`.
  Run Profiles use `model` ∈ `fake`, `openai_compat`, `anthropic`, `gemini` with matching nested
  sections; credentials are **environment variable names only**, never secret values in files.
- `profiles.py` owns **Run Profile** parsing, validation, naming resolution (bundled names,
  `.naqsha/profiles/`, `profiles/`, `examples/profiles/` paths per `load_raw_profile`), and bundled
  JSON/TOML under `bundled_profiles/`.
- `replay.py` holds trace helpers (`nap_messages_from_trace`, `observations_by_call_id`,
  `compare_replay`, ...). CLI `naqsha replay --re-execute` re-runs with recorded observations.
  `tests/redteam/` holds OWASP-linked regression tests; map in `docs/redteam/owasp-llm-top10-mapping.md`.
- `reflection/` owns the **Reflection Loop** boundary: **`SimpleReflectionLoop`**
  writes isolated **Reflection Patch** workspaces (never under the `naqsha` package
  tree). **`run_reliability_gate_subprocess`** runs `pytest` on
  `RELIABILITY_GATE_TEST_PATHS` before `ready_for_human_review` is true. There is no
  merge, apply, or hotpatch API; review workflow: `docs/reflection-patch-review.md`.
  **`naqsha reflect RUN_ID`** creates a patch from a QAOA trace (default workspace
  base `.naqsha/reflection-workspaces`). Do not import **Core Runtime**, **Tool Policy**,
  or **Approval Gate** from new reflection code.
- `wiring.py` owns **Run Profile → `CoreRuntime` wiring**: `build_runtime`,
  `build_trace_replay_runtime`, `inspect_policy_payload`. **`cli.py`** only parses arguments and
  dispatches to `wiring` and **`AgentWorkbench`**; it must not invent runtime semantics. Library
  embedders import from `naqsha.wiring` (or **`naqsha`** root re-exports), not from `cli` for
  construction.
- `eval_fixtures.py` owns schema-versioned regression fixture save/load helpers used by **`naqsha eval`** and **`AgentWorkbench.check_eval_fixture`**.
- `project.py` owns `.naqsha/` filesystem layout helpers (`naqsha init`).
- `trace_scan.py` lists traces by file mtime (e.g. `replay --latest`).
- `workbench/` owns **`AgentWorkbench`**: façade over profiles, replay, eval, reflection entry points **without importing `cli`**.

## First Extension Tasks

Good next tasks for a less-capable agent:

- Add tests before adding behavior.
- Pick exactly one phase from `docs/handoff/0001-v1-development-workflow.md` and finish it.
- Improve memory retrieval backends (beyond keyword + recency) without coupling `CoreRuntime`.
- Expand OWASP-mapped red-team fixtures under `tests/redteam/`.

## Phase Workflow

Use `docs/handoff/0001-v1-development-workflow.md` as the project execution plan.
Each new chat session should work on one phase only unless an earlier phase is
already complete and verified.

At the start of a phase:

- Read the required docs listed above.
- Confirm which phase is in scope.
- Identify the expected result and tests for that phase.
- Prefer tests first when the behavior is contract-shaped.

At the end of a phase:

- Run `uv run --extra dev pytest`.
- Run `uv run --extra dev ruff check .`.
- Update `docs/handoff/0001-v1-development-workflow.md` if phase status, sequencing,
  or acceptance criteria changed.
- Update this file when the phase reveals durable guidance future agents must keep.
- In the final response, state what changed, what was verified, and what the next
  phase inherits.

Keep phase state in the handoff document. Keep this file focused on standing rules.

## Things Not To Do

- Do not persist private chain-of-thought.
- Do not execute shell or file mutation without an Approval Gate.
- Do not let tool observations instruct the runtime.
- Do not add MCP to the Core Runtime.
- Do not replace QAOA Trace with provider-native chat transcripts.
- Do not make budgets advisory; exhausted budgets fail closed.
- Do not let Reflection Patches merge, hotpatch, or bypass human review.

## Packaging and releases

The public **PyPI distribution name**, **`import naqsha` package**, and **`naqsha` console script**
must stay **`naqsha`** (not `naqsh`). Typed package marker: `src/naqsha/py.typed`.

- Install-from-artifact regression tests live in `tests/test_packaging_install.py` (one shared
  wheel+sdist build per module; sdist install uses preinstalled `hatchling` and
  `--no-build-isolation` so CI does not need to download build backends).
- Maintainer checklist: `docs/release/pypi-checklist.md`.
- CI (when using GitHub Actions): `.github/workflows/ci.yml` syncs `dev` extras, runs Ruff, then
  the full pytest suite on Python 3.11 and 3.12.

## Completion Bar

A change is not done until it preserves:

- deterministic tests with fake models/tools
- append-only QAOA trace behavior
- runtime-enforced Tool Policy
- sanitized observations before trace, memory, or prompt reinjection
- explicit Run Profile choices instead of hidden environment-only config

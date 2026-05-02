# Agent Workbench and v1 Acceptance (checkpoint)

This note records a Phase 10 checkpoint after shipping the **Agent Workbench** surface on top of the existing Core Runtime.

## Shipped (product)

- **CLI**: `init`, `run` (with `--human`, stderr replay hint, `--version`), `replay` (with `--latest`), `trace inspect`, `profile show`, `tools list`, `eval save` / `eval check`, `reflect`, `improve` (alias of reflect + `IMPROVEMENT_NOTES.md` in patch workspace). Legacy `inspect-policy` retained.
- **Project layout**: `.naqsha/{traces,profiles,evals,reflection-workspaces}` via `naqsha init`; profiles resolvable as short names under `.naqsha/profiles/`.
- **Library**: `naqsha.AgentWorkbench`, `naqsha.wiring` (`build_runtime`, `build_trace_replay_runtime`, `inspect_policy_payload`), `eval_fixtures`, `project`, `trace_scan`.
- **Execution path**: Profile → `naqsha.wiring` → `CoreRuntime` (CLI does not own wiring logic).
- **Reflection**: richer `CANDIDATE.md` checklist; patch dirs include `IMPROVEMENT_NOTES.md`. No merge or hotpatch API.

## Reliability Gate

Full `pytest`, Ruff, packaging install tests, replay, memory, and red-team suites are the authoritative bar unchanged from prior phases.

## Residual / manual

Formal “v1 yes/no” still requires maintainer review of every ADR against behavior and OWASP fixture coverage; this document is informative, not a compliance claim.

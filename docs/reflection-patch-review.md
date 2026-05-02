# Reflection Patch review workflow

NAQSHA’s **Reflection Loop** may generate **Reflection Patches**: filesystem workspaces that hold human-readable candidate artifacts. Nothing in this flow applies code, changes **Tool Policy**, relaxes **Approval Gate** behavior, or hotpatches the **Core Runtime**.

## What gets produced

- **`naqsha reflect RUN_ID`** (or `SimpleReflectionLoop.propose_patch` in library code) creates a new directory under `--workspace-base` (default: `.naqsha/reflection-workspaces` in the current working directory).
- Each workspace is outside the installed `naqsha` package tree. Placing workspaces inside the package path is rejected.
- Typical files:
  - **`CANDIDATE.md`**: deterministic summary derived from the QAOA trace (failures, answer, tool chronology). Treat as **untrusted context** for humans only.
  - **`meta.json`**: run id, Reliability Gate outcome, and review-readiness flags.
  - **`READY_FOR_REVIEW.txt`**: present only if the Reliability Gate passed.
  - **`GATE_FAILED.txt`**: present if the gate did not pass; the folder must **not** be treated as review-ready.

## Reliability Gate

Before a patch is marked **ready for human review**, the loop runs **pytest** on a fixed corpus that matches the PRD **Reliability Gate** scope:

- Trace replay tests
- Protocol / NAP–QAOA schema tests
- Policy and trace integration tests
- SimpleMem-Cross golden tests
- OWASP-mapped red-team corpus (no external services)

The exact paths are `RELIABILITY_GATE_TEST_PATHS` in `naqsha.reflection.reliability_gate`. If you run `reflect` from an environment that is **not** a NAQSHA source checkout (no `tests/` tree), the gate cannot run and **`ready_for_human_review` stays false**.

Nested `naqsha reflect` invocations trigger a full pytest subprocess; expect noticeable wall time on large checkouts.

## Human review (mandatory)

- **`reliability_gate_passed`** and **`ready_for_human_review`** do **not** authorize a merge. They only record that the automated gate succeeded.
- There is **no** `merge`, `apply`, or `hotpatch` API on **`ReflectionPatch`**. Applying changes is a normal code review and version-control operation.
- Reviewers should treat **`CANDIDATE.md`** as notes, not instructions to the runtime, and should resist widening tool allowance or approvals unless justified by tests and threat model.

## Security expectations

Reflection modules do **not** import **Tool Policy**, **Approval Gate**, or **Core Runtime** implementations. Tests under `tests/test_reflection_loop.py` enforce absence of those bindings at source level and require patch workspaces to stay outside the `naqsha` package directory.

# Library: traces, eval fixtures, and reflection

This guide is for **Python embedders** wiring NAQSHA into an application. It complements the CLI; semantics live in **`Core Runtime`** wiring (`build_runtime`, `build_trace_replay_runtime`) and the higher-level **`AgentWorkbench`** façade.

## Imports

Import the common surfaces from the **`naqsha`** package root (**`load_run_profile`** and **`RunProfile`** are re-exported alongside **`AgentWorkbench`** and wiring helpers).

```python
from naqsha import (
    AgentWorkbench,
    RunProfile,
    build_runtime,
    build_trace_replay_runtime,
    inspect_policy_payload,
    load_run_profile,
)
```

Equivalent explicit imports live in **`naqsha.profiles`** if you prefer not to use re-exports.

Other useful surfaces used below:

```python
from naqsha.runtime import CoreRuntime, RunResult
from naqsha.replay import ReplayDiff, summarize_trace
```

## `AgentWorkbench` cookbook

**`AgentWorkbench`** wraps profile loading, runs, trace access, replay-with-recorded-observations, eval helpers, and reflection entry points. Construct it with a resolved **`RunProfile`** or a profile spec string (bundled name or path—same resolution rules as **`load_run_profile`**).

### Open a workbench

```python
from naqsha import AgentWorkbench, load_run_profile

wb = AgentWorkbench.from_profile_spec("local-fake")
# or:
wb = AgentWorkbench(load_run_profile("/path/to/profile.json"))
```

### Run a query

```python
result = wb.run("What is 2+2?")
# Optional interactive approvals for gated tools:
result = wb.run("Risky task", approve_prompt=True)
```

### Inspect effective Tool Policy

```python
snapshot = wb.policy_snapshot()  # dict from inspect_policy_payload(profile)
```

### Summarize and list traces

```python
runs = wb.list_runs()
latest = wb.latest_run()
if latest:
    summary = wb.summarize_run(latest)  # ReplaySummary: queries, observations, answer, failures
```

Paths relative to the current working directory:

```python
paths = wb.paths()  # WorkbenchPaths: cwd, trace_dir (from profile)
store = wb.trace_store()  # JsonlTraceStore(profile.trace_dir)
run_id = wb.latest_run()
if run_id:
    events = store.load(run_id)  # list[TraceEvent]
```

### Replay with re-execution (recorded observations)

**`replay_re_execute`** loads the first query from the reference trace, builds a replay **`CoreRuntime`** (scripted model + **`ToolScheduler`** with recorded observations), runs once, and compares the new trace to the reference. It returns **`(RunResult, ReplayDiff)`**.

```python
reference = wb.trace_store().load(run_id)
result, diff = wb.replay_re_execute(reference)
# diff.answer_matches, diff.tool_calls_match, reference vs replay run ids, etc.
```

Optional **`approve_prompt=True`** mirrors CLI behavior when policy requires approval during replay.

### Eval fixtures: save and check

Fixtures capture **expected answer** and **tool-call chronology** (`call_id` + `tool`) from a trace for regression checks. **`save_eval_fixture`** builds an **`EvalFixture`**, writes JSON to **`dest`**, and returns the object. **`check_eval_fixture`** verifies the reference trace still matches the fixture, re-executes replay, and returns a result **`dict`** (`passed`, `trace_matches_fixture`, `replay_answer_matches_reference`, `replay_tool_calls_match_reference`, plus identifiers—or an **`error`** key on failure).

```python
from pathlib import Path

fixture_path = Path(".naqsha/evals/smoke.json")
fx = wb.save_eval_fixture("smoke", run_id, fixture_path)

check = wb.check_eval_fixture(run_id, fixture_path)
assert check["passed"]
```

Typical failures surface as **`TraceReplayError`**, **`TraceReplayExhausted`**, or **`ReplayObservationMissing`** during replay; **`check_eval_fixture`** catches these and returns **`{"passed": False, "error": ...}`**.

### Reflection: propose a patch workspace

```python
patch = wb.propose_improvement(run_id)
if patch is None:
    ...
# patch is a ReflectionPatch from the reflection loop (or None if trace empty)
```

Optional **`workspace_parent`** overrides the directory that will contain isolated workspaces; default is **`.naqsha/reflection-workspaces`** under the current working directory (resolved).

---

## Lower-level **`CoreRuntime`** via **`build_runtime`**

Use **`build_runtime(profile, approve_prompt=False)`** when you want the same wiring as the library/CLI without **`AgentWorkbench`**. You get a **`CoreRuntime`** configured from the **`RunProfile`** (model client, Starter Tool Set, **Tool Policy**, **Approval Gate**, trace store, budgets, sanitizer, optional Memory Port).

```python
from naqsha import build_runtime, load_run_profile

profile = load_run_profile("local-fake")
runtime = build_runtime(profile)
result = runtime.run("Hello")
```

**`inspect_policy_payload(profile)`** returns a JSON-serializable policy/tool snapshot without constructing a full runtime.

---

## Trace replay and **`--re-execute`**

The CLI **`naqsha replay`** command can summarize a stored run or **re-run** it. **`--re-execute`** is the user-facing name for “run again using the **recorded model transcript** and **recorded tool observations**,” not live tool I/O.

Library equivalent: **`build_trace_replay_runtime(profile, reference_events, approve_prompt=False)`**, which:

1. Replays **NAP** messages from the reference trace via **`TraceReplayModelClient`** (**`nap_messages_from_trace`**).
2. Supplies **`ToolScheduler(recorded_observations=observations_by_call_id(reference_events))`** so approved tool calls resolve observations **by tool call id**.

**Call id mapping:** each **`observation`** trace row carries **`call_id`**; **`observations_by_call_id`** builds a map used at **`ToolScheduler.execute`** time. If an approved call’s id has no recorded observation, **`ReplayObservationMissing`** is raised (replay traces must be complete for those calls). Duplicate **`call_id`** entries in the reference trace are rejected (**`TraceReplayError`**).

Embedding without **`AgentWorkbench`**:

```python
from naqsha import build_trace_replay_runtime, load_run_profile
from naqsha.replay import first_query_from_trace

profile = load_run_profile("local-fake")
events = ...  # load reference TraceEvent list (e.g. JsonlTraceStore(...).load(run_id))
runtime = build_trace_replay_runtime(profile, events)
query = first_query_from_trace(events)
result = runtime.run(query)
```

---

## Eval fixtures and **`.naqsha/evals/`**

**`naqsha init`** creates **`.naqsha/evals/`** alongside traces and profiles. CLI **`naqsha eval save`** writes **` .naqsha/evals/<name>.json`** by default; the **`AgentWorkbench`** helpers take an explicit **`dest`** / **`fixture_path`**.

Fixtures are **schema-versioned** JSON (**`EvalFixture`**, **`EVAL_SCHEMA_VERSION`** in **`naqsha.eval_fixtures`**). They encode deterministic regression intent: same reference **run id**, **answer**, and ordered **`{call_id, tool}`** sequence as captured from the trace. **`check_eval_fixture`** combines trace-vs-fixture verification with a full replay comparison so behavior stays aligned with stored observations and scripted model steps.

---

## Reflection Loop (human review, no auto-merge)

The **Reflection Loop** (**`SimpleReflectionLoop`**, used by **`AgentWorkbench.propose_improvement`** and **`naqsha reflect`**) writes candidate artifacts under an **isolated workspace outside the installed `naqsha` package tree**. Typical files include **`CANDIDATE.md`**, **`meta.json`**, and gate markers (**`READY_FOR_REVIEW.txt`** / **`GATE_FAILED.txt`**).

Before **`ready_for_human_review`** can be true, a **Reliability Gate** runs **`pytest`** as a subprocess on the corpus defined by **`RELIABILITY_GATE_TEST_PATHS`** in **`naqsha.reflection.reliability_gate`** (trace replay, protocol/schema, policy/trace integration, SimpleMem-Cross goldens, OWASP-mapped tests—no external services). If the checkout has no **`tests/`** tree, the gate cannot run and review readiness stays false.

There is **no** merge, apply, or hotpatch API on **`ReflectionPatch`**. **`reliability_gate_passed`** does not authorize merging changes; reviewers apply edits through normal review and version control. Reflection code does not import **Tool Policy**, **Approval Gate**, or **Core Runtime** implementations—see **`docs/reflection-patch-review.md`** for expectations.

---

## Summary

| Concern | Primary API |
|--------|---------------|
| Day-to-day embedding | **`AgentWorkbench`** + **`load_run_profile`** |
| Custom orchestration | **`build_runtime`**, **`build_trace_replay_runtime`** |
| Policy introspection | **`inspect_policy_payload`** / **`workbench.policy_snapshot()`** |
| Replay without live tools | **`replay_re_execute`** or **`build_trace_replay_runtime`** + **`ToolScheduler`** recorded observations **by call id** |
| Regression JSON | **`.naqsha/evals/`**, **`save_eval_fixture`** / **`check_eval_fixture`** |
| Self-improvement artifacts | **`propose_improvement`**, isolated workspaces, pytest gate, mandatory human review |

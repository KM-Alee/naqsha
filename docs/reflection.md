# Reflection and Rollback

The **Reflection Loop** turns completed **Hierarchical QAOA Traces** into **Reflection Patches** — isolated workspaces under `.naqsha/reflection-workspaces/` with proposed code or configuration changes, a Reliability Gate result, and a human review flag.

!!! important "Safety default"
    `auto_merge = false` everywhere by default. No Reflection Patch can be merged without a Reliability Gate pass. There is no bypass.

---

## Generating a Reflection Patch

```bash
# From a completed run
naqsha reflect --profile workbench <run_id>

# Or: naqsha improve --profile workbench <run_id>
```

This creates a directory under `.naqsha/reflection-workspaces/reflection-patch-<stamp>/` with:

| File | Purpose |
|---|---|
| `CANDIDATE.md` | Deterministic summary from the trace — human context; still untrusted for automation |
| `meta.json` | Run ID, Reliability Gate outcome, review flags, timestamp |
| `READY_FOR_REVIEW.txt` | Present only when the Reliability Gate passed |
| `GATE_FAILED.txt` | Present when the gate failed; treat the folder as not merge-ready |
| `merge/` | Only present when `auto_merge = true` and the gate passed; contains the proposed file changes |

### Via the Python API

```python
from naqsha import AgentWorkbench

wb = AgentWorkbench.from_profile_spec("workbench")
patch = wb.propose_improvement(run_id="abc123")
print(patch.ready_for_human_review)   # True / False
print(patch.auto_merged)              # True only if auto_merge=true and gate passed
```

---

## Reliability Gate

The **Reliability Gate** runs `pytest` over the configured `gate_paths` in a subprocess **before** any merge:

```toml
[reflection]
reliability_gate = true
gate_paths       = ["tests/smoke/", "tests/regression/"]
```

A gate failure:

1. Sets `reliability_gate_passed = false` in `meta.json`.
2. Writes `GATE_FAILED.txt` to the patch workspace.
3. Prevents any merge, even when `auto_merge = true`.

`reliability_gate_passed` and `ready_for_human_review` **do not authorise a merge by themselves**. Applying changes is normal code review and version control. The reflection module intentionally does not import Tool Policy or Core Runtime.

---

## Automated Rollback Manager

Before any autonomous merge, `AutomatedRollbackManager`:

1. **Snapshots** `naqsha.toml` and `tools/` to `.naqsha/backups/<stamp>/`.
2. **Applies** the `merge/` payload into the team workspace root.
3. **Sets** `boot_status = pending` in the workspace state.
4. On the next `naqsha run` or `AgentWorkbench.run`, a **boot probe** runs a short health check.
5. If the probe **fails**: the workspace is restored from the latest snapshot and `PatchRolledBack` is emitted.
6. If the probe **passes**: `boot_status` is set to `stable`.

The manager prunes to the **5 most recent backups** automatically.

```python
from naqsha.reflection.rollback import AutomatedRollbackManager

manager = AutomatedRollbackManager(workspace_path=Path("."), sink=event_sink)
manager.snapshot(patch)
manager.apply_merge(patch)
manager.verify_boot_if_pending()  # called automatically by AgentWorkbench.run
```

---

## Configuring auto-merge

`auto_merge = false` is always the default. To opt in:

```toml
[reflection]
enabled          = true
auto_merge       = true   # opt-in; requires reliability_gate = true
reliability_gate = true
gate_paths       = ["tests/"]
```

!!! warning "auto_merge without reliability_gate"
    Setting `auto_merge = true` without `reliability_gate = true` is silently treated as `auto_merge = false`. The gate is non-negotiable.

---

## Human review with the Workbench TUI

The **Patch Review Panel** in the Workbench TUI lists all `reflection-patch-*` workspaces under `.naqsha/reflection-workspaces/`, shows a side-by-side diff preview, and routes **Approve** / **Reject** decisions:

```bash
naqsha run --profile workbench "anything"
# → opens WorkbenchApp; navigate to Patch Review panel
```

Approval routes to `approve_patch(patch_id)` in `naqsha.reflection.loop`, which:

1. Verifies the Reliability Gate passed.
2. Applies the merge.
3. Emits `PatchMerged` on the Event Bus (via `RuntimeBusReflectionSink`).

Rejection routes to `reject_patch(patch_id)`, which removes the workspace and emits nothing.

---

## ReflectionPatch

```python
from naqsha.reflection.base import ReflectionPatch

patch = ReflectionPatch(
    patch_id="reflection-patch-20260503T120000",
    workspace_path=Path(".naqsha/reflection-workspaces/reflection-patch-..."),
    run_id="abc123",
    reliability_gate_passed=True,
    ready_for_human_review=True,
    auto_merged=False,
)
```

| Field | Type | Description |
|---|---|---|
| `patch_id` | `str` | Unique patch identifier |
| `workspace_path` | `Path` | Absolute path to patch directory |
| `run_id` | `str` | Source run ID |
| `reliability_gate_passed` | `bool` | Whether pytest gate passed |
| `ready_for_human_review` | `bool` | Whether the patch is ready for human review |
| `auto_merged` | `bool` | Whether the patch was auto-merged (requires gate pass) |

---

## Event Bus integration

```python
from naqsha import RuntimeEventBus
from naqsha.core.events import PatchMerged, PatchRolledBack
from naqsha.workbench import RuntimeBusReflectionSink

bus = RuntimeEventBus()

@bus.subscribe
def on_merged(event: PatchMerged):
    print(f"Patch merged: {event.patch_id}")

@bus.subscribe
def on_rollback(event: PatchRolledBack):
    print(f"Patch rolled back: {event.patch_id}")

sink = RuntimeBusReflectionSink(bus)
wb = AgentWorkbench.from_profile_spec("workbench")
result = wb.run("improve this", patch_event_sink=sink)
```

---

## Isolation invariants

The `reflection/` package:

- **Never imports** `core/`, `tools/`, or `core/policy.py`.
- Patch workspaces must live **outside** the installed `naqsha` package tree.
- `create_isolated_workspace` rejects paths under the installed package tree.

---

## Further reading

- API: [`naqsha.reflection`](reference/reflection.md)
- ADR: [0006 — Autonomous Updates with Rollback](https://github.com/KM-Alee/naqsha/blob/main/docs/adr/0006-autonomous-updates-with-rollback.md)
- CLI patch review: [CLI and Workbench TUI — Patch review](cli.md#patch-review)

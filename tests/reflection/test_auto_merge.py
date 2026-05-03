"""Reflection auto-merge policy and Reliability Gate coupling."""

from __future__ import annotations

import json
from pathlib import Path

from naqsha.protocols.qaoa import answer_event, query_event
from naqsha.reflection.config import ReflectionTomlSettings
from naqsha.reflection.loop import SimpleReflectionLoop, noop_gate_runner


def _toml_with_reflection(**refl: bool | str) -> str:
    lines = [
        '[workspace]',
        'name = "t"',
        'orchestrator = "orch"',
        "",
        '[agents.orch]',
        'role = "orchestrator"',
        'model_adapter = "fake"',
        'tools = ["clock"]',
        "",
        "[reflection]",
        f"enabled = {str(refl.get('enabled', True)).lower()}",
        f"auto_merge = {str(refl.get('auto_merge', False)).lower()}",
        f"reliability_gate = {str(refl.get('reliability_gate', True)).lower()}",
        "",
    ]
    return "\n".join(lines)


def test_auto_merge_true_applies_merge_after_gate_pass(tmp_path: Path) -> None:
    team = tmp_path / "team"
    team.mkdir()
    body = _toml_with_reflection(enabled=True, auto_merge=True, reliability_gate=True)
    (team / "naqsha.toml").write_text(body, encoding="utf-8")

    rw = tmp_path / "reflection-ws"
    rw.mkdir()

    events = [query_event("run1", "hi"), answer_event("run1", "ok")]
    loop = SimpleReflectionLoop(
        workspace_parent=rw,
        team_workspace=team,
        project_root=tmp_path,
        gate_runner=noop_gate_runner,
        reflection_settings=ReflectionTomlSettings(
            enabled=True,
            auto_merge=True,
            reliability_gate=True,
        ),
    )
    patch = loop.propose_patch(events)
    assert patch is not None
    assert patch.auto_merged is True
    tom = (team / "naqsha.toml").read_text(encoding="utf-8")
    assert "# naqsha: reflection auto-merge marker" in tom
    assert (team / ".naqsha" / "boot_status").read_text(encoding="utf-8").strip() == "pending"

    meta = json.loads((patch.workspace / "meta.json").read_text(encoding="utf-8"))
    assert meta["auto_merged"] is True


def test_auto_merge_false_leaves_workspace_unchanged(tmp_path: Path) -> None:
    team = tmp_path / "team"
    team.mkdir()
    original = _toml_with_reflection(enabled=True, auto_merge=False, reliability_gate=True)
    (team / "naqsha.toml").write_text(original, encoding="utf-8")
    rw = tmp_path / "rw"
    rw.mkdir()

    loop = SimpleReflectionLoop(
        workspace_parent=rw,
        team_workspace=team,
        project_root=tmp_path,
        gate_runner=noop_gate_runner,
        reflection_settings=ReflectionTomlSettings(
            enabled=True,
            auto_merge=False,
            reliability_gate=True,
        ),
    )
    patch = loop.propose_patch([query_event("r", "q"), answer_event("r", "a")])
    assert patch is not None
    assert patch.auto_merged is False
    assert (team / "naqsha.toml").read_text(encoding="utf-8") == original
    assert not (team / ".naqsha" / "boot_status").exists()

    meta = json.loads((patch.workspace / "meta.json").read_text(encoding="utf-8"))
    assert meta["auto_merged"] is False


def test_auto_merge_blocked_without_reliability_gate(tmp_path: Path) -> None:
    team = tmp_path / "team"
    team.mkdir()
    (team / "naqsha.toml").write_text(
        _toml_with_reflection(enabled=True, auto_merge=True, reliability_gate=False),
        encoding="utf-8",
    )
    rw = tmp_path / "rw"
    rw.mkdir()

    loop = SimpleReflectionLoop(
        workspace_parent=rw,
        team_workspace=team,
        project_root=tmp_path,
        gate_runner=noop_gate_runner,
        reflection_settings=ReflectionTomlSettings(
            enabled=True,
            auto_merge=True,
            reliability_gate=False,
        ),
    )
    patch = loop.propose_patch([query_event("r", "q"), answer_event("r", "a")])
    assert patch is not None
    assert patch.auto_merged is False


def test_no_naqsha_toml_never_auto_merges(tmp_path: Path) -> None:
    team = tmp_path / "team"
    team.mkdir()
    rw = tmp_path / "rw"
    rw.mkdir()

    loop = SimpleReflectionLoop(
        workspace_parent=rw,
        team_workspace=team,
        project_root=tmp_path,
        gate_runner=noop_gate_runner,
        reflection_settings=ReflectionTomlSettings(
            enabled=True,
            auto_merge=True,
            reliability_gate=True,
        ),
    )
    patch = loop.propose_patch([query_event("r", "q"), answer_event("r", "a")])
    assert patch is not None
    assert patch.auto_merged is False


def test_gate_runs_even_when_toml_disables_reliability_gate_for_auto_merge(tmp_path: Path) -> None:
    team = tmp_path / "team"
    team.mkdir()
    (team / "naqsha.toml").write_text(
        _toml_with_reflection(enabled=True, auto_merge=True, reliability_gate=False),
        encoding="utf-8",
    )
    rw = tmp_path / "rw"
    rw.mkdir()

    gate_calls: list[Path] = []

    def counting_gate(root: Path):
        gate_calls.append(root)
        return noop_gate_runner(root)

    loop = SimpleReflectionLoop(
        workspace_parent=rw,
        team_workspace=team,
        project_root=tmp_path,
        gate_runner=counting_gate,
        reflection_settings=ReflectionTomlSettings(
            enabled=True,
            auto_merge=True,
            reliability_gate=False,
        ),
    )
    patch = loop.propose_patch([query_event("r", "q"), answer_event("r", "a")])
    assert patch is not None
    assert len(gate_calls) == 1
    assert patch.auto_merged is False


def test_runtime_bus_reflection_sink_emits_typed_events() -> None:
    from naqsha.core.event_bus import RuntimeEventBus
    from naqsha.core.events import PatchMerged, PatchRolledBack
    from naqsha.workbench import RuntimeBusReflectionSink

    seen: list[object] = []
    bus = RuntimeEventBus()
    bus.subscribe(lambda e: seen.append(e))
    sink = RuntimeBusReflectionSink(bus, default_agent_id="orch")

    sink.patch_merged(run_id="r1", agent_id="", patch_id="pid", auto_merged=True)
    sink.patch_rolled_back(run_id="r1", agent_id="", patch_id="pid", reason="bad boot")

    assert isinstance(seen[0], PatchMerged)
    assert seen[0].patch_id == "pid"
    assert isinstance(seen[1], PatchRolledBack)

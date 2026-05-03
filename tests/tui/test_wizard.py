"""Tests for ``naqsha init`` Textual wizard."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("textual")

from naqsha.core.budgets import BudgetLimits
from naqsha.orchestration.topology import parse_team_topology_file
from naqsha.tui.wizard.init import render_workspace_toml, run_init_wizard


def test_render_workspace_toml_round_trip(tmp_path: Path) -> None:
    b = BudgetLimits()
    body = render_workspace_toml(
        workspace_name='Team "A"',
        workspace_description="",
        trace_dir=".naqsha/traces",
        sanitizer_max_chars=4000,
        auto_approve=False,
        approval_required_tiers="write,high",
        memory_db_path=".naqsha/memory.db",
        num_total_agents=3,
        memory_embeddings=True,
        reflection_enabled=True,
        reflection_auto_merge=False,
        reflection_reliability_gate=True,
        orch_budget_max_steps=b.max_steps,
        orch_budget_max_tool_calls=b.max_tool_calls,
        orch_budget_wall_seconds=b.wall_clock_seconds,
        orch_budget_per_tool_seconds=b.per_tool_seconds,
        orch_max_retries=3,
        worker_budget_max_steps=b.max_steps,
        worker_budget_max_tool_calls=b.max_tool_calls,
        worker_budget_wall_seconds=b.wall_clock_seconds,
        worker_budget_per_tool_seconds=b.per_tool_seconds,
        worker_max_retries=3,
    )
    path = tmp_path / "naqsha.toml"
    path.write_text(body, encoding="utf-8")
    topo = parse_team_topology_file(path)
    assert topo.workspace.name == 'Team "A"'
    assert topo.memory.embeddings is True
    assert topo.reflection.enabled is True
    assert topo.reflection.auto_merge is False
    assert "orch" in topo.agents and "worker1" in topo.agents and "worker2" in topo.agents


def test_wizard_autosave_writes_valid_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NAQSHA_TEST_WIZARD_AUTOSAVE", "1")
    out = run_init_wizard(cwd=tmp_path, profile_name="wizard-test")
    assert out.is_file()
    topo = parse_team_topology_file(out)
    assert topo.workspace.orchestrator == "orch"

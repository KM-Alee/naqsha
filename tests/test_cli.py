"""CLI command-level smoke tests."""

from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from naqsha import cli
from naqsha.core.budgets import BudgetLimits
from naqsha.tui.wizard.init import render_workspace_toml


def test_cli_inspect_policy_bundled_profile_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    out = StringIO()
    with redirect_stdout(out):
        code = cli.main(["inspect-policy", "--profile", "local-fake"])
    assert code == 0
    payload = json.loads(out.getvalue())
    assert payload["resolved_profile"]["name"] == "local-fake"
    names = [t["name"] for t in payload["tools"]]
    assert "clock" in names


def test_cli_run_and_replay_with_bundled_profile(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    buf = StringIO()
    with redirect_stdout(buf):
        assert cli.main(["run", "--profile", "local-fake", "ping"]) == 0
    result = json.loads(buf.getvalue().strip())
    run_id = result["run_id"]
    assert result["failed"] is False

    buf2 = StringIO()
    with redirect_stdout(buf2):
        assert cli.main(["replay", "--profile", "local-fake", run_id]) == 0
    summary = json.loads(buf2.getvalue().strip())
    assert summary["run_id"] == run_id
    assert summary["queries"] == ["ping"]


def test_cli_replay_re_execute_matches_live_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    buf = StringIO()
    with redirect_stdout(buf):
        assert cli.main(["run", "--profile", "local-fake", "ping"]) == 0
    run_id = json.loads(buf.getvalue())["run_id"]

    out2 = StringIO()
    with redirect_stdout(out2):
        code = cli.main(["replay", "--profile", "local-fake", "--re-execute", run_id])
    assert code == 0
    payload = json.loads(out2.getvalue())
    assert payload["reference_run_id"] == run_id
    assert payload["answer_matches_reference"] is True
    assert payload["tool_calls_match_reference"] is True
    assert payload["replay_run_id"] != run_id


def test_cli_profile_not_found_stderr(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli.main(["run", "--profile", "no-such-bundle-name-zzz", "query"]) == 2
    err = capsys.readouterr().err
    assert "profile error" in err.lower()


def test_cli_run_with_profile_file_path(tmp_path: Path, monkeypatch) -> None:
    traces = tmp_path / "t"
    traces.mkdir()
    profile_path = tmp_path / "p.json"
    profile_path.write_text(
        json.dumps(
            {
                "name": "file-backed",
                "model": "fake",
                "trace_dir": traces.name,
                "tool_root": ".",
                "fake_model": {
                    "messages": [
                        {
                            "kind": "answer",
                            "text": "from profile file",
                        }
                    ]
                },
            },
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    buf = StringIO()
    with redirect_stdout(buf):
        code = cli.main(["run", "--profile", str(profile_path), "q"])
    assert code == 0
    assert json.loads(buf.getvalue())["answer"] == "from profile file"


def test_cli_run_simplemem_cross_profile(tmp_path: Path, monkeypatch) -> None:
    traces = tmp_path / "t"
    traces.mkdir()
    db_file = "cross-cli.sqlite"
    profile_path = tmp_path / "cross.json"
    profile_path.write_text(
        json.dumps(
            {
                "name": "cross-cli",
                "model": "fake",
                "trace_dir": traces.name,
                "tool_root": ".",
                "memory_adapter": "simplemem_cross",
                "memory_cross_database": db_file,
                "memory_cross_project": "cli-smoke",
                "fake_model": {
                    "messages": [
                        {"kind": "answer", "text": "smoke with durable memory."},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    buf = StringIO()
    with redirect_stdout(buf):
        assert cli.main(["run", "--profile", str(profile_path), "hello"]) == 0
    assert json.loads(buf.getvalue())["answer"] == "smoke with durable memory."
    assert (tmp_path / db_file).is_file()


def test_cli_trace_dir_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    override = tmp_path / "override_traces"
    override.mkdir(exist_ok=True)
    buf = StringIO()
    with redirect_stdout(buf):
        cli.main(["run", "--profile", "local-fake", "--trace-dir", str(override), "once"])
    run_id = json.loads(buf.getvalue())["run_id"]

    summary_buf = StringIO()
    with redirect_stdout(summary_buf):
        cli.main(["replay", "--trace-dir", str(override), run_id])
    assert json.loads(summary_buf.getvalue())["run_id"] == run_id


def test_cli_inspect_defaults_without_explicit_profile(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    buf = StringIO()
    with redirect_stdout(buf):
        assert cli.main(["inspect-policy"]) == 0
    assert json.loads(buf.getvalue())["resolved_profile"]["name"] == "local-fake"


def test_cli_bare_without_workspace_hints_init(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli.main([]) == 2
    err = capsys.readouterr().err.lower()
    assert "naqsha.toml" in err
    assert "init" in err


def test_cli_bare_with_toml_no_tui_exits_plain(tmp_path: Path, monkeypatch, capsys) -> None:
    b = BudgetLimits()
    (tmp_path / "naqsha.toml").write_text(
        render_workspace_toml(
            workspace_name="cli-bare-smoke",
            workspace_description="",
            trace_dir=".naqsha/traces",
            sanitizer_max_chars=4000,
            auto_approve=False,
            approval_required_tiers="write,high",
            memory_db_path=".naqsha/memory.db",
            num_total_agents=2,
            memory_embeddings=False,
            reflection_enabled=False,
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
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NAQSHA_NO_TUI", "1")
    assert cli.main([]) == 2
    err = capsys.readouterr().err.lower()
    assert "tui" in err

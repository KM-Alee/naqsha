"""Agent Workbench, eval fixtures, and profile resolution tests."""

from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from naqsha import cli
from naqsha.eval_fixtures import EvalFixture, load_fixture, save_fixture
from naqsha.profiles import load_run_profile
from naqsha.workbench import AgentWorkbench


def test_init_creates_layout_and_profile(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    buf = StringIO()
    with redirect_stdout(buf):
        assert cli.main(["init"]) == 0
    out = json.loads(buf.getvalue())
    assert out["initialized"] is True
    assert (tmp_path / ".naqsha" / "traces").is_dir()
    assert (tmp_path / ".naqsha" / "evals").is_dir()
    prof = tmp_path / ".naqsha" / "profiles" / "workbench.json"
    assert prof.is_file()
    p = load_run_profile("workbench")
    assert p.name == "workbench"
    assert p.trace_dir == (tmp_path / ".naqsha" / "traces").resolve()


def test_cli_version_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0


def test_tools_list_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    buf = StringIO()
    with redirect_stdout(buf):
        assert cli.main(["tools", "list", "--profile", "local-fake"]) == 0
    tools = json.loads(buf.getvalue())
    assert isinstance(tools, list)
    names = {t["name"] for t in tools}
    assert "clock" in names


def test_profile_show_alias(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    buf = StringIO()
    with redirect_stdout(buf):
        assert cli.main(["profile", "show", "--profile", "local-fake"]) == 0
    payload = json.loads(buf.getvalue())
    assert payload["resolved_profile"]["name"] == "local-fake"


def test_eval_save_and_check(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    buf = StringIO()
    with redirect_stdout(buf):
        assert cli.main(["run", "--profile", "local-fake", "ping"]) == 0
    run_id = json.loads(buf.getvalue())["run_id"]

    save_buf = StringIO()
    with redirect_stdout(save_buf):
        assert cli.main(["eval", "save", "--profile", "local-fake", run_id, "smoke"]) == 0
    save_out = json.loads(save_buf.getvalue())
    assert (tmp_path / ".naqsha" / "evals" / "smoke.json").is_file()
    assert "smoke" in save_out.get("fixture", {}).get("name", "")

    check_buf = StringIO()
    with redirect_stdout(check_buf):
        code = cli.main(
            ["eval", "check", "--profile", "local-fake", run_id, "--name", "smoke"]
        )
    assert code == 0
    result = json.loads(check_buf.getvalue())
    assert result["passed"] is True


def test_workbench_from_profile_spec(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cli.main(["init"])
    wb = AgentWorkbench.from_profile_spec("workbench")
    r = wb.run("hello")
    assert r.failed is False
    assert wb.latest_run() == r.run_id


def test_eval_fixture_roundtrip(tmp_path: Path) -> None:
    fix = EvalFixture(
        schema_version=1,
        name="n",
        reference_run_id="rid",
        expected_answer="a",
        expected_tool_calls=[{"call_id": "1", "tool": "clock"}],
    )
    path = tmp_path / "e.json"
    save_fixture(path, fix)
    loaded = load_fixture(path)
    assert loaded == fix


def test_replay_latest_flag(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    buf = StringIO()
    with redirect_stdout(buf):
        assert cli.main(["run", "--profile", "local-fake", "first"]) == 0
    json.loads(buf.getvalue())["run_id"]
    buf2 = StringIO()
    with redirect_stdout(buf2):
        assert cli.main(["run", "--profile", "local-fake", "second"]) == 0
    latest_id = json.loads(buf2.getvalue())["run_id"]

    summary_buf = StringIO()
    with redirect_stdout(summary_buf):
        assert cli.main(["replay", "--profile", "local-fake", "--latest"]) == 0
    summary = json.loads(summary_buf.getvalue())
    assert summary["run_id"] == latest_id
    assert summary["queries"] == ["second"]

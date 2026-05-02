"""CLI command-level smoke tests."""

from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from naqsha import cli


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

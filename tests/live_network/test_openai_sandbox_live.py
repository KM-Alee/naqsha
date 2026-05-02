"""Opt-in live tests: OpenAI + starter tools via CLI (costs API usage).

Run from repo root::

    export OPENAI_API_KEY=...
    NAQSHA_LIVE=1 uv run --extra dev pytest tests/live_network -v --tb=short

Without ``NAQSHA_LIVE=1`` these tests are skipped (CI-safe).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SANDBOX = REPO_ROOT / "sandbox" / "live"


pytestmark = [
    pytest.mark.live_network,
    pytest.mark.skipif(
        os.environ.get("NAQSHA_LIVE") != "1",
        reason="Set NAQSHA_LIVE=1 to run live_network tests.",
    ),
]


def _need_key() -> None:
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        pytest.skip("OPENAI_API_KEY must be set for live_network tests.")


def _naqsha(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "naqsha", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env=os.environ.copy(),
    )


@pytest.fixture(autouse=True)
def _live_network_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    SANDBOX.mkdir(parents=True, exist_ok=True)
    ws = SANDBOX / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "read-smoke.txt").write_text("NAQSHA_LIVE_READ_SMOKE\n", encoding="utf-8")
    monkeypatch.chdir(SANDBOX)


def test_inspect_policy_smoke() -> None:
    _need_key()
    proc = _naqsha(["inspect-policy", "--profile", "profiles/openai-live.json"], cwd=SANDBOX)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["resolved_profile"]["name"] == "openai-live-sandbox"


def test_openai_run_answer_only_human() -> None:
    _need_key()
    proc = _naqsha(
        [
            "run",
            "--profile",
            "profiles/openai-live.json",
            "--human",
            "--no-hint",
            "Reply with the single digit 7 and nothing else.",
        ],
        cwd=SANDBOX,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "7" in proc.stdout


def test_openai_clock_tool_roundtrip() -> None:
    """Forces at least one tool turn if the model follows instructions."""
    _need_key()
    proc = _naqsha(
        [
            "run",
            "--profile",
            "profiles/openai-live.json",
            "--human",
            "--no-hint",
            "Use the clock tool exactly once and quote its output briefly.",
        ],
        cwd=SANDBOX,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    reply = proc.stdout.strip()
    assert reply


def test_openai_calculator_tool() -> None:
    _need_key()
    proc = _naqsha(
        [
            "run",
            "--profile",
            "profiles/openai-live.json",
            "--human",
            "--no-hint",
            "Use the calculator tool to compute 6 * 7. Reply with the integer result only.",
        ],
        cwd=SANDBOX,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "42" in proc.stdout


def test_openai_read_file_tool() -> None:
    _need_key()
    proc = _naqsha(
        [
            "run",
            "--profile",
            "profiles/openai-live.json",
            "--human",
            "--no-hint",
            "Use read_file on read-smoke.txt once. The answer must include NAQSHA_LIVE_READ_SMOKE.",
        ],
        cwd=SANDBOX,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "NAQSHA_LIVE_READ_SMOKE" in proc.stdout


def test_openai_human_approval_tool() -> None:
    _need_key()
    proc = _naqsha(
        [
            "run",
            "--profile",
            "profiles/openai-live.json",
            "--human",
            "--no-hint",
            'Call human_approval once with reason pytest-live. Then reply exactly: OK.',
        ],
        cwd=SANDBOX,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "OK" in proc.stdout

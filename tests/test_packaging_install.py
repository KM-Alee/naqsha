"""Wheel/sdist install checks in an isolated venv (release hardening)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _py(venv: Path) -> Path:
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _naqsha(venv: Path) -> Path:
    if sys.platform == "win32":
        return venv / "Scripts" / "naqsha.exe"
    return venv / "bin" / "naqsha"


def _run(
    args: list[str],
    *,
    check: bool = True,
    capture_output: bool = False,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=check,
        capture_output=capture_output,
        text=True,
        cwd=cwd,
        env=os.environ.copy(),
    )


@pytest.fixture(scope="module")
def built_dist_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("dist")
    proc = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--sdist", "--outdir", str(out)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    return out


def test_wheel_contains_py_typed(built_dist_dir: Path) -> None:
    wheels = list(built_dist_dir.glob("naqsha-*.whl"))
    assert len(wheels) == 1, wheels
    with zipfile.ZipFile(wheels[0]) as zf:
        names = zf.namelist()
    assert "naqsha/py.typed" in names


def _fresh_venv(parent: Path) -> Path:
    venv = parent / "venv"
    _run([sys.executable, "-m", "venv", str(venv)], capture_output=True)
    return venv


def test_wheel_install_import_and_cli_smoke(
    built_dist_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    wheel = next(built_dist_dir.glob("naqsha-*.whl"))
    venv = _fresh_venv(tmp_path / "wheel-venv")
    _run([str(_py(venv)), "-m", "pip", "install", "--quiet", str(wheel)], capture_output=True)
    _run(
        [str(_py(venv)), "-c", "from naqsha import CoreRuntime, RunResult, RuntimeConfig"],
        capture_output=True,
    )
    proc = subprocess.run(
        [str(_naqsha(venv)), "run", "--profile", "local-fake", "ping"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout.strip())
    assert payload.get("failed") is False
    assert "run_id" in payload


def test_sdist_install_import_and_cli_smoke(
    built_dist_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use ``--no-build-isolation`` so the sdist build does not require fetching hatchling."""
    monkeypatch.chdir(tmp_path)
    sdist = next(built_dist_dir.glob("naqsha-*.tar.gz"))
    venv = _fresh_venv(tmp_path / "sdist-venv")
    py = str(_py(venv))
    _run([py, "-m", "pip", "install", "--quiet", "hatchling"], capture_output=True)
    _run(
        [py, "-m", "pip", "install", "--quiet", "--no-build-isolation", str(sdist)],
        capture_output=True,
    )
    proc = subprocess.run(
        [str(_naqsha(venv)), "run", "--profile", "local-fake", "ping"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout.strip())
    assert payload.get("failed") is False

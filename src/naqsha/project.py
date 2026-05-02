"""Agent Workbench project layout under ``.naqsha/``."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

NAQSHA_DIR = ".naqsha"


def project_root(cwd: Path | None = None) -> Path:
    return (cwd or Path.cwd()).resolve()


def traces_dir(root: Path | None = None) -> Path:
    return project_root(root) / NAQSHA_DIR / "traces"


def profiles_dir(root: Path | None = None) -> Path:
    return project_root(root) / NAQSHA_DIR / "profiles"


def evals_dir(root: Path | None = None) -> Path:
    return project_root(root) / NAQSHA_DIR / "evals"


def reflection_workspaces_dir(root: Path | None = None) -> Path:
    return project_root(root) / NAQSHA_DIR / "reflection-workspaces"


def default_workbench_profile_path(root: Path | None = None) -> Path:
    return profiles_dir(root) / "workbench.json"


def init_agent_project(
    root: Path | None = None,
    *,
    profile_name: str = "workbench",
    copy_bundled_fake: bool = True,
) -> Path:
    """Create ``.naqsha/{traces,profiles,evals,reflection-workspaces}`` and a default profile.

    Returns path to the created profile file.
    """

    base = project_root(root)
    n = base / NAQSHA_DIR
    (n / "traces").mkdir(parents=True, exist_ok=True)
    (n / "profiles").mkdir(parents=True, exist_ok=True)
    (n / "evals").mkdir(parents=True, exist_ok=True)
    (n / "reflection-workspaces").mkdir(parents=True, exist_ok=True)

    profile_path = profiles_dir(base) / f"{profile_name}.json"
    if not profile_path.exists() and copy_bundled_fake:
        bundled = files("naqsha.bundled_profiles") / "local-fake.json"
        raw = bundled.read_bytes().decode("utf-8")
        data = json.loads(raw)
        data["name"] = profile_name
        # Paths relative to profile file directory (``.naqsha/profiles``).
        data["trace_dir"] = str(Path("..") / "traces")
        data["tool_root"] = str(Path("..") / "..")
        profile_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    elif not profile_path.exists():
        profile_path.write_text(
            json.dumps(
                {
                    "name": profile_name,
                    "model": "fake",
                    "trace_dir": str(Path("..") / "traces"),
                    "tool_root": str(Path("..") / ".."),
                    "allowed_tools": None,
                    "memory_adapter": "none",
                    "memory_token_budget": 512,
                    "auto_approve": False,
                    "approval_required_tiers": ["write", "high"],
                    "sanitizer_max_chars": 4000,
                    "budgets": {
                        "max_steps": 8,
                        "max_tool_calls": 16,
                        "wall_clock_seconds": 30.0,
                        "per_tool_seconds": 5.0,
                        "max_model_tokens": None,
                    },
                    "fake_model": {"messages": None},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    readme = n / "README.txt"
    if not readme.exists():
        readme.write_text(
            "NAQSHA Agent Workbench project data.\n"
            "- profiles/: Run Profile JSON/TOML (paths resolve relative to each file)\n"
            "- traces/: append-only QAOA Trace JSONL files\n"
            "- evals/: saved regression expectations (JSON)\n"
            "- reflection-workspaces/: isolated Reflection Patches for reviewed improvement\n",
            encoding="utf-8",
        )
    return profile_path


def ensure_project_layout(root: Path | None = None) -> None:
    """Create ``.naqsha`` subdirs if missing (no profile file)."""

    base = project_root(root)
    for sub in ("traces", "profiles", "evals", "reflection-workspaces"):
        (base / NAQSHA_DIR / sub).mkdir(parents=True, exist_ok=True)

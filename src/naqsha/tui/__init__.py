"""NAQSHA Workbench TUI (optional ``[tui]`` extra)."""

from naqsha.tui.app import (
    WorkbenchApp,
    build_workbench_app,
    cli_should_use_tui,
    tui_available,
)

__all__ = [
    "WorkbenchApp",
    "build_workbench_app",
    "cli_should_use_tui",
    "tui_available",
]

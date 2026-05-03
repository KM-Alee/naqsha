"""Workbench TUI panels."""

from naqsha.tui.panels.budget import BudgetPanel
from naqsha.tui.panels.chat import ChatPanel
from naqsha.tui.panels.flame import FlamePanel
from naqsha.tui.panels.memory import MemoryBrowserPanel
from naqsha.tui.panels.patch_review import PatchReviewPanel
from naqsha.tui.panels.span_tree import SpanTreePanel

__all__ = [
    "BudgetPanel",
    "ChatPanel",
    "FlamePanel",
    "MemoryBrowserPanel",
    "PatchReviewPanel",
    "SpanTreePanel",
]

"""Hard Budget Limits."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic


class BudgetExceeded(RuntimeError):
    """Raised when a hard budget limit is exhausted."""


@dataclass(frozen=True)
class BudgetLimits:
    max_steps: int = 8
    max_tool_calls: int = 16
    wall_clock_seconds: float = 30.0
    per_tool_seconds: float = 5.0
    max_model_tokens: int | None = None


@dataclass
class BudgetMeter:
    limits: BudgetLimits
    started_at: float = field(default_factory=monotonic)
    steps: int = 0
    tool_calls: int = 0

    def consume_step(self) -> None:
        self._check_wall_clock()
        self.steps += 1
        if self.steps > self.limits.max_steps:
            raise BudgetExceeded("Maximum step budget exceeded.")

    def consume_tool_call(self) -> None:
        self._check_wall_clock()
        self.tool_calls += 1
        if self.tool_calls > self.limits.max_tool_calls:
            raise BudgetExceeded("Maximum tool call budget exceeded.")

    def check_wall_clock(self) -> None:
        """Fail closed if the run wall-clock budget is exhausted."""

        self._check_wall_clock()

    def _check_wall_clock(self) -> None:
        if monotonic() - self.started_at > self.limits.wall_clock_seconds:
            raise BudgetExceeded("Wall-clock budget exceeded.")

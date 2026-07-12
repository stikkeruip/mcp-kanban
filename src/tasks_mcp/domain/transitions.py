"""Transition policy: the pluggable rule for moving tasks between columns.

The board is free-movement in v1, but the *seam* for strictness is built
now. A future ``LinearTransitionPolicy`` (enforce backlog → in_progress →
testing → done) is a new class in this module, selected in config — adding
it must require zero changes to existing code. That is the test of whether
this seam was built correctly.
"""

from __future__ import annotations

from typing import Protocol

from tasks_mcp.domain.task import Status


class TransitionPolicy(Protocol):
    """The contract every transition policy implements."""

    def can_move(self, current: Status, target: Status) -> bool:
        """Return True if a task may move from ``current`` to ``target``."""
        ...


class FreeTransitionPolicy:
    """Any column to any column. The v1 default."""

    def can_move(self, current: Status, target: Status) -> bool:
        """Always allow the move."""
        return True

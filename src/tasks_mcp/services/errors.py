"""Typed service-layer exceptions.

Service methods raise these — they never return error strings. The MCP
adapter (or any other consumer) catches them and formats a clean,
human-readable message for its own audience.
"""

from __future__ import annotations


class TaskServiceError(Exception):
    """Base class for all service-layer failures."""


class TaskNotFound(TaskServiceError):
    """No task exists with the requested id."""

    def __init__(self, task_id: int) -> None:
        self.task_id = task_id
        super().__init__(f"no task with id {task_id}")


class ValidationError(TaskServiceError):
    """Input failed validation (empty title, unknown status/priority, ...)."""


class InvalidTransition(TaskServiceError):
    """The transition policy refused a column move."""

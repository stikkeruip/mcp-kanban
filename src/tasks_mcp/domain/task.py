"""Core task types: the ``Task`` dataclass and its ``Status``/``Priority`` enums.

This module is pure domain. It performs no I/O and imports nothing from the
rest of the project. How a task is *stored* (JSON tags, ISO datetimes,
integer booleans) is the storage layer's problem, never this module's.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Status(str, Enum):
    """The four kanban columns, declared in board order.

    Subclasses ``str`` so values serialize cleanly and compare equal to their
    string form (``Status.BACKLOG == "backlog"``) while keeping enum safety.
    Iterating ``Status`` yields columns in canonical board order.
    """

    BACKLOG = "backlog"
    IN_PROGRESS = "in_progress"
    TESTING = "testing"
    DONE = "done"


class Priority(str, Enum):
    """Task priority. Subclasses ``str`` for clean serialization."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


@dataclass
class Task:
    """A single task on the board.

    A plain data holder — no persistence methods, no ``.save()``. Coupling
    the domain to storage would invert the dependency rule.

    ``id`` is ``None`` before the task has been persisted; the repository
    assigns it on insert. ``tags`` is a real ``list[str]`` here; serialization
    to a storage format is not the domain's concern.
    """

    id: int | None
    title: str
    description: str | None
    status: Status
    priority: Priority
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    archived: bool

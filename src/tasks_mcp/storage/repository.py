"""The abstract ``TaskRepository`` — the persistence contract.

The service layer codes against this interface only. Adding a new backend
(Postgres, in-memory, ...) means implementing this ABC and selecting it in
the composition root; no existing code changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from tasks_mcp.domain.task import Priority, Status, Task


class TaskRepository(ABC):
    """Every persistence operation the service layer needs."""

    @abstractmethod
    def add(self, task: Task) -> Task:
        """Persist a new task (``task.id`` must be None).

        Returns the stored task with its assigned id.
        """

    @abstractmethod
    def get(self, task_id: int) -> Task | None:
        """Return the task with ``task_id``, or None if it does not exist.

        Archived tasks are returned too — archiving hides tasks from
        listings, it does not destroy them.
        """

    @abstractmethod
    def list(
        self,
        *,
        status: Status | None = None,
        tag: str | None = None,
        priority: Priority | None = None,
        include_archived: bool = False,
    ) -> list[Task]:
        """Return tasks matching every given filter, oldest first.

        Archived tasks are excluded unless ``include_archived`` is True.
        """

    @abstractmethod
    def update(self, task: Task) -> Task:
        """Persist all mutable fields of an existing task (matched by id).

        Raises ``RowNotFound`` if no row with ``task.id`` exists.
        """

    @abstractmethod
    def archive(self, task_id: int) -> Task | None:
        """Set the ``archived`` flag on a task (soft delete).

        Returns the archived task, or None if it does not exist. This is a
        low-level flag flip: it does not touch ``updated_at`` — timestamp
        management is the service layer's responsibility.
        """

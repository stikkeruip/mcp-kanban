"""``TaskService`` — every operation on the board lives here.

Responsibilities that belong to this layer and nowhere else:

* **Validation** — non-empty titles, known status/priority values, clean
  tags, and existence checks before edit/move/archive.
* **Timestamps** — ``created_at``/``updated_at`` are set here (via an
  injectable clock), not by database defaults, so behavior is explicit
  and testable.
* **Transition checks** — ``move_task`` consults the injected
  ``TransitionPolicy``. With the free policy this never refuses, but the
  call is in place: switching to a strict policy later requires zero
  changes to this method.

Dependencies arrive by constructor injection; this class never constructs
a repository or policy itself — that is the composition root's job.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from tasks_mcp.domain.task import Priority, Status, Task
from tasks_mcp.domain.transitions import TransitionPolicy
from tasks_mcp.services.errors import InvalidTransition, TaskNotFound, ValidationError
from tasks_mcp.storage.repository import TaskRepository


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskService:
    """The internal API for the personal kanban board."""

    def __init__(
        self,
        repo: TaskRepository,
        transitions: TransitionPolicy,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._repo = repo
        self._transitions = transitions
        self._now = now

    # -- operations -----------------------------------------------------

    def add_task(
        self,
        title: str,
        description: str | None = None,
        priority: Priority | str = Priority.NORMAL,
        tags: list[str] | None = None,
        link: str | None = None,
    ) -> Task:
        """Create a task in the backlog and return it (with its new id)."""
        now = self._now()
        task = Task(
            id=None,
            title=self._clean_title(title),
            description=self._clean_description(description),
            status=Status.BACKLOG,
            priority=self._coerce_priority(priority),
            tags=self._clean_tags(tags),
            created_at=now,
            updated_at=now,
            archived=False,
            link=self._clean_link(link),
        )
        return self._repo.add(task)

    def get_task(self, task_id: int) -> Task:
        """Return one task (archived or not). Raises ``TaskNotFound``."""
        task = self._repo.get(task_id)
        if task is None:
            raise TaskNotFound(task_id)
        return task

    def list_tasks(
        self,
        *,
        status: Status | str | None = None,
        tag: str | None = None,
        priority: Priority | str | None = None,
        include_archived: bool = False,
    ) -> list[Task]:
        """Return tasks matching every given filter, oldest first.

        Archived tasks are hidden unless ``include_archived`` is True.
        """
        return self._repo.list(
            status=self._coerce_status(status) if status is not None else None,
            tag=tag,
            priority=self._coerce_priority(priority) if priority is not None else None,
            include_archived=include_archived,
        )

    def edit_task(
        self,
        task_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        priority: Priority | str | None = None,
        tags: list[str] | None = None,
        link: str | None = None,
    ) -> Task:
        """Update the given fields of a task; omitted (None) fields keep their value.

        Passing an empty string for ``description`` or ``link`` clears it.
        At least one field must be provided. Status changes go through
        ``move_task``, not here — moving columns is a distinct operation
        with its own rules.
        """
        if (
            title is None
            and description is None
            and priority is None
            and tags is None
            and link is None
        ):
            raise ValidationError("nothing to update: provide at least one field")
        task = self.get_task(task_id)
        if title is not None:
            task.title = self._clean_title(title)
        if description is not None:
            task.description = self._clean_description(description)
        if priority is not None:
            task.priority = self._coerce_priority(priority)
        if tags is not None:
            task.tags = self._clean_tags(tags)
        if link is not None:
            task.link = self._clean_link(link)
        task.updated_at = self._now()
        return self._repo.update(task)

    def move_task(self, task_id: int, target_status: Status | str) -> Task:
        """Move a task to another column, if the transition policy allows it."""
        target = self._coerce_status(target_status)
        task = self.get_task(task_id)
        if not self._transitions.can_move(task.status, target):
            raise InvalidTransition(
                f"cannot move task {task_id} from '{task.status.value}' "
                f"to '{target.value}'"
            )
        task.status = target
        task.updated_at = self._now()
        return self._repo.update(task)

    def archive_task(self, task_id: int) -> Task:
        """Soft-delete a task: hide it from default listings, keep it in the DB.

        Idempotent — archiving an already-archived task returns it unchanged.
        """
        task = self.get_task(task_id)
        if task.archived:
            return task
        task.archived = True
        task.updated_at = self._now()
        return self._repo.update(task)

    def get_board(self) -> dict:
        """Return the board: unarchived tasks grouped by column.

        Fixed shape — always all four columns, in board order, even when
        empty — so rendering is predictable:

            {"columns": [{"status": Status.BACKLOG, "tasks": [Task, ...]}, ...]}
        """
        grouped: dict[Status, list[Task]] = {status: [] for status in Status}
        for task in self._repo.list():
            grouped[task.status].append(task)
        return {
            "columns": [
                {"status": status, "tasks": grouped[status]} for status in Status
            ]
        }

    # -- validation & coercion (service-owned, nowhere else) -------------

    @staticmethod
    def _clean_title(title: str) -> str:
        if not isinstance(title, str) or not title.strip():
            raise ValidationError("title must be a non-empty string")
        return title.strip()

    @staticmethod
    def _clean_description(description: str | None) -> str | None:
        if description is None:
            return None
        if not isinstance(description, str):
            raise ValidationError("description must be a string")
        return description.strip() or None

    @staticmethod
    def _clean_link(link: str | None) -> str | None:
        if link is None:
            return None
        if not isinstance(link, str):
            raise ValidationError("link must be a string")
        return link.strip() or None

    @staticmethod
    def _clean_tags(tags: list[str] | None) -> list[str]:
        if tags is None:
            return []
        if not isinstance(tags, list):
            raise ValidationError("tags must be a list of strings")
        cleaned: list[str] = []
        for tag in tags:
            if not isinstance(tag, str) or not tag.strip():
                raise ValidationError(f"invalid tag {tag!r}: tags must be non-empty strings")
            stripped = tag.strip()
            if stripped not in cleaned:  # dedupe, preserving order
                cleaned.append(stripped)
        return cleaned

    @staticmethod
    def _coerce_status(value: Status | str) -> Status:
        try:
            return Status(value)
        except ValueError:
            valid = ", ".join(s.value for s in Status)
            raise ValidationError(f"invalid status {value!r}: expected one of {valid}")

    @staticmethod
    def _coerce_priority(value: Priority | str) -> Priority:
        try:
            return Priority(value)
        except ValueError:
            valid = ", ".join(p.value for p in Priority)
            raise ValidationError(f"invalid priority {value!r}: expected one of {valid}")

"""MCP tool definitions — thin adapters over ``TaskService``.

Each tool: parse args → call one service method → format the result.
Service exceptions are caught and surfaced as clean, human-readable
``ToolError`` messages (never a stack trace).

Tool names are the external contract — keep them stable. Docstrings and
type hints ARE the schema Claude sees: they are load-bearing, written for
Claude as the reader.
"""

from __future__ import annotations

from contextlib import contextmanager

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from tasks_mcp.domain.task import Task
from tasks_mcp.services.errors import TaskServiceError
from tasks_mcp.services.task_service import TaskService


def task_to_dict(task: Task) -> dict:
    """Format a domain Task as a JSON-ready dict (the tool output shape)."""
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status.value,
        "priority": task.priority.value,
        "tags": task.tags,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "archived": task.archived,
    }


@contextmanager
def _service_errors():
    """Translate typed service errors into clean MCP tool errors."""
    try:
        yield
    except TaskServiceError as exc:
        raise ToolError(str(exc)) from exc


def register_tools(mcp: FastMCP, service: TaskService) -> None:
    """Register the seven board tools on a FastMCP server instance."""

    @mcp.tool
    def add_task(
        title: str,
        description: str | None = None,
        priority: str = "normal",
        tags: list[str] | None = None,
    ) -> dict:
        """Add a new task to the board. It lands in the 'backlog' column.

        Args:
            title: Short name of the task (required, non-empty).
            description: Optional longer free-text detail.
            priority: One of 'low', 'normal', 'high'. Defaults to 'normal'.
            tags: Optional list of labels for filtering, e.g. ["work", "errand"].

        Returns the created task, including its assigned numeric id.
        """
        with _service_errors():
            return task_to_dict(
                service.add_task(
                    title, description=description, priority=priority, tags=tags
                )
            )

    @mcp.tool
    def list_tasks(
        status: str | None = None,
        tag: str | None = None,
        priority: str | None = None,
        include_archived: bool = False,
    ) -> list[dict]:
        """List tasks, optionally filtered. All filters combine with AND.

        Args:
            status: Only tasks in this column: 'backlog', 'in_progress',
                'testing', or 'done'.
            tag: Only tasks carrying exactly this tag.
            priority: Only tasks with this priority: 'low', 'normal', 'high'.
            include_archived: Also include archived (soft-deleted) tasks.
                Off by default.

        Returns matching tasks, oldest first. For a column-by-column view of
        the whole board, prefer get_board.
        """
        with _service_errors():
            return [
                task_to_dict(t)
                for t in service.list_tasks(
                    status=status,
                    tag=tag,
                    priority=priority,
                    include_archived=include_archived,
                )
            ]

    @mcp.tool
    def get_task(task_id: int) -> dict:
        """Get the full detail of one task by its numeric id.

        Works for archived tasks too.
        """
        with _service_errors():
            return task_to_dict(service.get_task(task_id))

    @mcp.tool
    def edit_task(
        task_id: int,
        title: str | None = None,
        description: str | None = None,
        priority: str | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        """Edit a task's title, description, priority, and/or tags.

        Only the fields you pass are changed; omitted fields keep their
        current value. Pass an empty string for description to clear it.
        Passing tags replaces the whole tag list. To change a task's column,
        use move_task instead.

        Returns the updated task.
        """
        with _service_errors():
            return task_to_dict(
                service.edit_task(
                    task_id,
                    title=title,
                    description=description,
                    priority=priority,
                    tags=tags,
                )
            )

    @mcp.tool
    def move_task(task_id: int, target_status: str) -> dict:
        """Move a task to another kanban column.

        Args:
            task_id: Numeric id of the task to move.
            target_status: Destination column: 'backlog', 'in_progress',
                'testing', or 'done'.

        Returns the updated task.
        """
        with _service_errors():
            return task_to_dict(service.move_task(task_id, target_status))

    @mcp.tool
    def archive_task(task_id: int) -> dict:
        """Archive a task (soft delete): it disappears from listings and the
        board but stays in the database. There is no hard delete.

        Returns the archived task.
        """
        with _service_errors():
            return task_to_dict(service.archive_task(task_id))

    @mcp.tool
    def get_board() -> dict:
        """Get the whole kanban board: unarchived tasks grouped by column.

        Always returns all four columns in board order — backlog,
        in_progress, testing, done — even when empty:

            {"columns": [{"status": "backlog", "tasks": [...]}, ...]}

        Use this to render or summarize the board.
        """
        with _service_errors():
            board = service.get_board()
            return {
                "columns": [
                    {
                        "status": column["status"].value,
                        "tasks": [task_to_dict(t) for t in column["tasks"]],
                    }
                    for column in board["columns"]
                ]
            }

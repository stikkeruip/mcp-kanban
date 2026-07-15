"""MCP tool definitions — thin adapters over ``TaskService``.

Each tool: parse args → call one service method → format the result.
Service exceptions are caught and surfaced as clean, human-readable
``ToolError`` messages (never a stack trace).

Tool names are the external contract — keep them stable. Docstrings and
type hints ARE the schema Claude sees: they are load-bearing, written for
Claude as the reader.
"""

from __future__ import annotations

import webbrowser
from contextlib import contextmanager

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError

from tasks_mcp.config import AppConfig
from tasks_mcp.domain.task import Status, Task
from tasks_mcp.resume import launch_terminal, parse_resume_link
from tasks_mcp.services.errors import TaskServiceError
from tasks_mcp.services.task_service import TaskService
from tasks_mcp.web.autostart import ensure_web_running


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
        "link": task.link,
    }


@contextmanager
def _service_errors():
    """Translate typed service errors into clean MCP tool errors."""
    try:
        yield
    except TaskServiceError as exc:
        raise ToolError(str(exc)) from exc


def register_tools(
    mcp: FastMCP, service: TaskService, config: AppConfig | None = None
) -> None:
    """Register the board tools on a FastMCP server instance.

    ``config`` enables the ``open_board`` tool (it needs the web view's
    host/port); without it every other tool still works.
    """

    @mcp.tool(annotations={"destructiveHint": False, "openWorldHint": False})
    def add_task(
        title: str,
        description: str | None = None,
        priority: str = "normal",
        tags: list[str] | None = None,
        link: str | None = None,
    ) -> dict:
        """Add a new task to the board. It lands in the 'backlog' column.

        Args:
            title: Short name of the task (required, non-empty).
            description: Optional longer free-text detail.
            priority: One of 'low', 'normal', 'high'. Defaults to 'normal'.
            tags: Optional list of labels for filtering, e.g. ["work", "errand"].
            link: Optional pointer back to the task's context — a URL or a
                command that reopens it. To park a Claude Code chat for
                later, store its resume command here, e.g.
                "cd C:\\dev\\myproject; claude -r <session-id>".

        Returns the created task, including its assigned numeric id.
        """
        with _service_errors():
            return task_to_dict(
                service.add_task(
                    title,
                    description=description,
                    priority=priority,
                    tags=tags,
                    link=link,
                )
            )

    @mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
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

    @mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
    def get_task(task_id: int) -> dict:
        """Get the full detail of one task by its numeric id.

        Works for archived tasks too.
        """
        with _service_errors():
            return task_to_dict(service.get_task(task_id))

    @mcp.tool(
        annotations={
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }
    )
    def edit_task(
        task_id: int,
        title: str | None = None,
        description: str | None = None,
        priority: str | None = None,
        tags: list[str] | None = None,
        link: str | None = None,
    ) -> dict:
        """Edit a task's title, description, priority, tags, and/or link.

        Only the fields you pass are changed; omitted fields keep their
        current value. Pass an empty string for description or link to clear
        it. Passing tags replaces the whole tag list. To change a task's
        column, use move_task instead.

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
                    link=link,
                )
            )

    @mcp.tool(
        annotations={
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }
    )
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

    @mcp.tool(
        annotations={
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }
    )
    def archive_task(task_id: int) -> dict:
        """Archive a task (soft delete): it disappears from listings and the
        board but stays in the database. There is no hard delete.

        Returns the archived task.
        """
        with _service_errors():
            return task_to_dict(service.archive_task(task_id))

    @mcp.tool(annotations={"destructiveHint": False, "openWorldHint": False})
    async def resume_task(task_id: int | None = None, ctx: Context = None) -> dict:
        """Resume the Claude Code chat linked to a task, in a new terminal.

        With task_id: opens that task's linked chat directly. Without it:
        shows the user an interactive picker (rendered by the client) of all
        tasks whose link is a resume command, and opens the selected one.

        Only links of the exact shape "cd <dir>; claude -r <session-id>"
        can be launched. The new terminal opens in the task's original
        directory — required, because claude only finds sessions from the
        directory they were created in.
        """
        with _service_errors():
            if task_id is not None:
                task = service.get_task(task_id)
                parsed = parse_resume_link(task.link)
                if parsed is None:
                    raise ToolError(
                        f"task {task_id} has no resume-command link "
                        '(expected "cd <dir>; claude -r <session-id>")'
                    )
                launch_terminal(*parsed)
                return {
                    "launched": True,
                    "task_id": task.id,
                    "title": task.title,
                    "directory": parsed[0],
                    "session_id": parsed[1],
                }

            candidates = [
                (task, parsed)
                for task in service.list_tasks()
                if (parsed := parse_resume_link(task.link)) is not None
            ]
            if not candidates:
                raise ToolError("no tasks have resume-command links")
            options = [
                f"#{task.id} {task.title} [{task.status.value}]"
                for task, _ in candidates
            ]
            result = await ctx.elicit(
                "Which parked chat do you want to resume?", response_type=options
            )
            if getattr(result, "action", "accept") != "accept":
                return {"launched": False, "cancelled": True}
            choice = getattr(result, "data", None)
            if choice not in options:
                raise ToolError(f"unexpected selection: {choice!r}")
            task, parsed = candidates[options.index(choice)]
            launch_terminal(*parsed)
            return {
                "launched": True,
                "task_id": task.id,
                "title": task.title,
                "directory": parsed[0],
                "session_id": parsed[1],
            }

    @mcp.tool(annotations={"destructiveHint": False, "openWorldHint": False})
    def open_board() -> dict:
        """Open the drag-and-drop kanban board in the default web browser.

        Starts the local web server in the background first if nothing is
        listening yet. The board reads the same database as these tools, so
        changes made in the browser are immediately visible here, and
        changes made here appear on the board within a few seconds.
        """
        if config is None:
            raise ToolError("open_board is unavailable: server was built without config")
        with _service_errors():
            spawned = ensure_web_running(config) is not None
            url = f"http://{config.web_host}:{config.web_port}"
            webbrowser.open(url)
            return {"url": url, "started_server": spawned}

    @mcp.tool(annotations={"destructiveHint": False, "openWorldHint": False})
    async def browse_board(ctx: Context = None) -> dict:
        """Browse the kanban board interactively inside the client.

        One tool call opens a chain of client-rendered pickers (no model
        round-trips between steps, so navigation is instant): choose a
        column, choose a task, then act on it — move it, archive it, or
        resume its linked Claude Code chat. Navigation entries (→/←) switch
        columns; "✕ close" ends the session.

        Returns a summary of every action performed, for a one-line recap.
        """
        _CLOSE = "✕ close board"
        _BACK = "← back to column"
        with _service_errors():
            columns = list(Status)
            col_idx = 0
            actions: list[str] = []

            while True:
                status = columns[col_idx]
                tasks = service.list_tasks(status=status)
                nav_next = f"→ {columns[(col_idx + 1) % len(columns)].value}"
                nav_prev = f"← {columns[(col_idx - 1) % len(columns)].value}"
                task_options = [
                    f"#{t.id} {t.title}"
                    + (f" [{t.priority.value}]" if t.priority.value != "normal" else "")
                    + (" ⧉" if t.link else "")
                    for t in tasks
                ]
                counts = "  ".join(
                    f"{'▶' if s is status else ' '}{s.value}:{len(service.list_tasks(status=s))}"
                    for s in columns
                )
                result = await ctx.elicit(
                    f"Board — {counts}\nColumn '{status.value}' "
                    f"({len(tasks)} task{'s' if len(tasks) != 1 else ''}). Pick a task or navigate:",
                    response_type=[nav_next, nav_prev, *task_options, _CLOSE],
                )
                if getattr(result, "action", None) != "accept":
                    break
                choice = getattr(result, "data", _CLOSE)
                if choice == _CLOSE:
                    break
                if choice == nav_next:
                    col_idx = (col_idx + 1) % len(columns)
                    continue
                if choice == nav_prev:
                    col_idx = (col_idx - 1) % len(columns)
                    continue

                task = service.get_task(int(choice[1:].split(" ", 1)[0]))
                move_options = [
                    f"move to {s.value}" for s in columns if s is not task.status
                ]
                action_options = list(move_options)
                if parse_resume_link(task.link):
                    action_options.insert(0, "resume linked chat")
                action_options += ["archive", _BACK]
                result = await ctx.elicit(
                    f"#{task.id} {task.title}\n"
                    + (f"{task.description}\n" if task.description else "")
                    + f"priority: {task.priority.value}"
                    + (f" | tags: {', '.join(task.tags)}" if task.tags else ""),
                    response_type=action_options,
                )
                if getattr(result, "action", None) != "accept":
                    break
                action = getattr(result, "data", _BACK)
                if action == _BACK:
                    continue
                if action == "resume linked chat":
                    launch_terminal(*parse_resume_link(task.link))
                    actions.append(f"resumed chat linked to #{task.id} {task.title}")
                elif action == "archive":
                    service.archive_task(task.id)
                    actions.append(f"archived #{task.id} {task.title}")
                elif action.startswith("move to "):
                    target = action.removeprefix("move to ")
                    service.move_task(task.id, target)
                    actions.append(f"moved #{task.id} {task.title} to {target}")

            return {"actions": actions or ["browsed the board, no changes"]}

    @mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
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

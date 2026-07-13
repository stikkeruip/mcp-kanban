"""SQLite implementation of ``TaskRepository``.

Everything about *how* a Task is stored lives in this one file: the
row ↔ ``Task`` mapping (``_row_to_task`` / ``_task_to_params``), tags as a
JSON array in a TEXT column, datetimes as ISO-8601 strings, ``archived`` as
0/1 — and the translation of ``sqlite3`` errors into storage exceptions.
Nothing outside this module knows any of that.

Connections are opened in WAL mode so a future consumer (e.g. an HTML board
view) can read the same database while the MCP server writes.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from tasks_mcp.domain.task import Priority, Status, Task
from tasks_mcp.storage.errors import ConstraintViolation, RowNotFound, StorageError
from tasks_mcp.storage.repository import TaskRepository

_COLUMNS = "id, title, description, status, priority, tags, created_at, updated_at, archived"


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection configured for this application.

    Autocommit mode (explicit transactions where needed), WAL journaling,
    and name-based row access. Pass ``":memory:"`` for an in-memory database
    (used by the test suite).
    """
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


class SqliteTaskRepository(TaskRepository):
    """``TaskRepository`` backed by a single SQLite ``tasks`` table.

    Takes an already-connected, already-migrated connection: opening the
    database and running migrations are the composition root's jobs
    (see ``tasks_mcp.mcp.server``).
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # -- TaskRepository ------------------------------------------------

    def add(self, task: Task) -> Task:
        """Insert a new task and return it with its assigned id."""
        if task.id is not None:
            raise StorageError(f"cannot add a task that already has id={task.id}")
        cur = self._execute(
            """
            INSERT INTO tasks
                (title, description, status, priority, tags,
                 created_at, updated_at, archived)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            self._task_to_params(task),
        )
        return replace(task, id=cur.lastrowid)

    def get(self, task_id: int) -> Task | None:
        """Return the task with ``task_id`` (archived or not), or None."""
        row = self._execute(
            f"SELECT {_COLUMNS} FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return self._row_to_task(row) if row is not None else None

    def list(
        self,
        *,
        status: Status | None = None,
        tag: str | None = None,
        priority: Priority | None = None,
        include_archived: bool = False,
    ) -> list[Task]:
        """Return tasks matching every given filter, oldest first."""
        clauses: list[str] = []
        params: list[object] = []
        if not include_archived:
            clauses.append("archived = 0")
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if priority is not None:
            clauses.append("priority = ?")
            params.append(priority.value)
        if tag is not None:
            # Exact-match against elements of the JSON tags array.
            clauses.append(
                "EXISTS (SELECT 1 FROM json_each(tasks.tags) WHERE json_each.value = ?)"
            )
            params.append(tag)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._execute(
            f"SELECT {_COLUMNS} FROM tasks{where} ORDER BY id", tuple(params)
        ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def update(self, task: Task) -> Task:
        """Persist all mutable fields of an existing task."""
        if task.id is None:
            raise StorageError("cannot update a task that has no id")
        cur = self._execute(
            """
            UPDATE tasks
               SET title = ?, description = ?, status = ?, priority = ?,
                   tags = ?, created_at = ?, updated_at = ?, archived = ?
             WHERE id = ?
            """,
            self._task_to_params(task) + (task.id,),
        )
        if cur.rowcount == 0:
            raise RowNotFound(f"no task with id={task.id}")
        return task

    def archive(self, task_id: int) -> Task | None:
        """Flip the ``archived`` flag; return the task or None if absent."""
        self._execute("UPDATE tasks SET archived = 1 WHERE id = ?", (task_id,))
        return self.get(task_id)

    # -- mapping (the ONLY place that knows the storage format) --------

    @staticmethod
    def _task_to_params(task: Task) -> tuple:
        """Serialize a Task's mutable fields to SQL parameters, in column order."""
        return (
            task.title,
            task.description,
            task.status.value,
            task.priority.value,
            json.dumps(task.tags),
            task.created_at.isoformat(),
            task.updated_at.isoformat(),
            1 if task.archived else 0,
        )

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        """Deserialize a database row into a domain Task."""
        return Task(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            status=Status(row["status"]),
            priority=Priority(row["priority"]),
            tags=json.loads(row["tags"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            archived=bool(row["archived"]),
        )

    # -- error translation ---------------------------------------------

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a statement, translating sqlite errors into storage errors."""
        try:
            return self._conn.execute(sql, params)
        except sqlite3.IntegrityError as exc:
            raise ConstraintViolation(str(exc)) from exc
        except sqlite3.Error as exc:
            raise StorageError(str(exc)) from exc

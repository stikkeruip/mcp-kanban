"""Shared composition helpers: config → concrete object graph.

Two entry points consume ``TaskService`` — the MCP server and the web
view — and both need the same wiring: open the database, run migrations,
build the repository and transition policy, construct the service. This
module is the one shared place for that, so the composition roots cannot
drift apart. Nothing here contains business logic.
"""

from __future__ import annotations

from tasks_mcp.config import AppConfig
from tasks_mcp.domain.transitions import FreeTransitionPolicy, TransitionPolicy
from tasks_mcp.services.task_service import TaskService
from tasks_mcp.storage.migrations.runner import run_migrations
from tasks_mcp.storage.sqlite_repository import SqliteTaskRepository, connect

# The documented hook for future policies: add a class in
# tasks_mcp.domain.transitions, register it here, select it via the
# TASKS_MCP_TRANSITIONS env var. No other code changes.
_POLICIES: dict[str, type] = {
    "free": FreeTransitionPolicy,
}


def build_policy(name: str) -> TransitionPolicy:
    """Instantiate the transition policy selected in config."""
    try:
        return _POLICIES[name]()
    except KeyError:
        valid = ", ".join(sorted(_POLICIES))
        raise ValueError(
            f"unknown transition policy {name!r}: expected one of {valid}"
        ) from None


def build_service(config: AppConfig) -> TaskService:
    """Open + migrate the database and return a fully wired TaskService."""
    conn = connect(config.db_path)
    run_migrations(conn)
    repo = SqliteTaskRepository(conn)
    return TaskService(repo, build_policy(config.transition_policy))

"""Composition root: the ONLY place concrete classes are wired together.

Read config → open the database → run migrations → build the policy →
construct the service → register tools → serve. Everything else in the
codebase receives its dependencies; nothing else constructs them.
"""

from __future__ import annotations

from fastmcp import FastMCP

from tasks_mcp.config import AppConfig, load_config
from tasks_mcp.domain.transitions import FreeTransitionPolicy, TransitionPolicy
from tasks_mcp.mcp.tools import register_tools
from tasks_mcp.services.task_service import TaskService
from tasks_mcp.storage.migrations.runner import run_migrations
from tasks_mcp.storage.sqlite_repository import SqliteTaskRepository, connect

# The documented hook for future policies: add a class in
# tasks_mcp.domain.transitions, register it here, select it via the
# TASKS_MCP_TRANSITIONS env var. No other code changes.
_POLICIES: dict[str, type] = {
    "free": FreeTransitionPolicy,
}


def _build_policy(name: str) -> TransitionPolicy:
    """Instantiate the transition policy selected in config."""
    try:
        return _POLICIES[name]()
    except KeyError:
        valid = ", ".join(sorted(_POLICIES))
        raise ValueError(
            f"unknown transition policy {name!r}: expected one of {valid}"
        ) from None


def build_server(config: AppConfig | None = None) -> FastMCP:
    """Wire the full dependency graph and return a ready-to-run server."""
    cfg = config if config is not None else load_config()

    conn = connect(cfg.db_path)
    run_migrations(conn)
    repo = SqliteTaskRepository(conn)
    service = TaskService(repo, _build_policy(cfg.transition_policy))

    mcp = FastMCP(
        name="tasks-mcp",
        instructions=(
            "A personal kanban board with four columns: backlog, "
            "in_progress, testing, done. Use get_board to see everything, "
            "add_task to capture work, and move_task to advance it."
        ),
    )
    register_tools(mcp, service)
    return mcp


def main() -> None:
    """Entry point (``tasks-mcp`` script): serve over stdio."""
    build_server().run()


if __name__ == "__main__":
    main()

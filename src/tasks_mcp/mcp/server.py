"""MCP entry point and composition root.

Read config → build the service (shared wiring) → register tools → serve
over stdio. Everything else receives its dependencies.
"""

from __future__ import annotations

from fastmcp import FastMCP

from tasks_mcp.config import AppConfig, load_config
from tasks_mcp.mcp.tools import register_tools
from tasks_mcp.wiring import build_service


def build_server(config: AppConfig | None = None) -> FastMCP:
    """Wire the full dependency graph and return a ready-to-run server."""
    cfg = config if config is not None else load_config()
    service = build_service(cfg)

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
    """Entry point (``tasks-mcp`` script): serve over stdio.

    Also ensures the shared browser board is up (unless disabled via
    ``TASKS_MCP_WEB_AUTOSTART=0``): whichever session starts first spawns
    it; everyone else finds the port occupied and moves on.
    """
    cfg = load_config()
    if cfg.web_autostart:
        from tasks_mcp.web.autostart import ensure_web_running

        ensure_web_running(cfg)
    build_server(cfg).run()


if __name__ == "__main__":
    main()

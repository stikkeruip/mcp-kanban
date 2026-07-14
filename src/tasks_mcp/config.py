"""Config resolution — the one place that reads the environment.

No scattered ``os.getenv`` calls across the codebase: everything the app
can be configured with is resolved here into a small typed object.

Environment variables:

* ``TASKS_MCP_DB`` — path to the SQLite database file.
  Default: ``~/.local/share/tasks-mcp/tasks.db`` (directory is created
  if missing).
* ``TASKS_MCP_TRANSITIONS`` — transition policy name. Default ``"free"``
  (any column to any column). This is the documented hook for a future
  ``"linear"`` policy; the mapping from name to policy class lives in the
  composition root (``tasks_mcp.mcp.server``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

ENV_DB_PATH = "TASKS_MCP_DB"
ENV_TRANSITION_POLICY = "TASKS_MCP_TRANSITIONS"
ENV_WEB_HOST = "TASKS_MCP_WEB_HOST"
ENV_WEB_PORT = "TASKS_MCP_WEB_PORT"
ENV_WEB_AUTOSTART = "TASKS_MCP_WEB_AUTOSTART"

DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "tasks-mcp" / "tasks.db"
DEFAULT_TRANSITION_POLICY = "free"
DEFAULT_WEB_HOST = "127.0.0.1"  # local-only by default; it's a personal board
DEFAULT_WEB_PORT = 8765


@dataclass(frozen=True)
class AppConfig:
    """Resolved application configuration."""

    db_path: Path
    transition_policy: str
    web_host: str = DEFAULT_WEB_HOST
    web_port: int = DEFAULT_WEB_PORT
    web_autostart: bool = True


def load_config(env: Mapping[str, str] = os.environ) -> AppConfig:
    """Resolve configuration from the environment (injectable for tests).

    Ensures the database's parent directory exists.
    """
    raw_path = env.get(ENV_DB_PATH)
    db_path = Path(raw_path).expanduser() if raw_path else DEFAULT_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    policy = env.get(ENV_TRANSITION_POLICY, DEFAULT_TRANSITION_POLICY)
    return AppConfig(
        db_path=db_path,
        transition_policy=policy,
        web_host=env.get(ENV_WEB_HOST, DEFAULT_WEB_HOST),
        web_port=int(env.get(ENV_WEB_PORT, DEFAULT_WEB_PORT)),
        web_autostart=env.get(ENV_WEB_AUTOSTART, "1").lower()
        not in ("0", "false", "no", "off"),
    )

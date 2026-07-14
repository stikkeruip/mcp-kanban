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

DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "tasks-mcp" / "tasks.db"
DEFAULT_TRANSITION_POLICY = "free"


@dataclass(frozen=True)
class AppConfig:
    """Resolved application configuration."""

    db_path: Path
    transition_policy: str


def load_config(env: Mapping[str, str] = os.environ) -> AppConfig:
    """Resolve configuration from the environment (injectable for tests).

    Ensures the database's parent directory exists.
    """
    raw_path = env.get(ENV_DB_PATH)
    db_path = Path(raw_path).expanduser() if raw_path else DEFAULT_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    policy = env.get(ENV_TRANSITION_POLICY, DEFAULT_TRANSITION_POLICY)
    return AppConfig(db_path=db_path, transition_policy=policy)

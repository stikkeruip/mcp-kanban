"""Opportunistic web-view autostart.

Any MCP session can call :func:`ensure_web_running` at startup: if nothing
is listening on the configured web port yet, the web server is spawned as
a *detached* background process running ``python -m tasks_mcp.web``. If two
sessions race, both may spawn — the loser exits immediately on "port in
use", so the outcome is always exactly one web server.

The spawned process gets the caller's resolved config passed through the
environment, so it serves the same database the MCP session uses. Its
stdio is fully redirected to devnull: the caller may be an MCP server
whose stdout carries the protocol, and a child inheriting it would corrupt
the stream.

The web server deliberately outlives the sessions that started it — it is
a shared, local-only convenience, stopped by killing the process or
rebooting.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys

from tasks_mcp.config import (
    ENV_DB_PATH,
    ENV_TRANSITION_POLICY,
    ENV_WEB_HOST,
    ENV_WEB_PORT,
    AppConfig,
)


def _port_in_use(host: str, port: int) -> bool:
    """True if something is already accepting connections on host:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def ensure_web_running(config: AppConfig) -> subprocess.Popen | None:
    """Spawn the web view in the background unless one is already up.

    Returns the spawned process handle, or None if a server was already
    listening. Never raises — a broken web spawn must not take down the
    MCP session that attempted it.
    """
    try:
        if _port_in_use(config.web_host, config.web_port):
            return None

        env = {
            **os.environ,
            ENV_DB_PATH: str(config.db_path),
            ENV_TRANSITION_POLICY: config.transition_policy,
            ENV_WEB_HOST: config.web_host,
            ENV_WEB_PORT: str(config.web_port),
        }
        creationflags = 0
        kwargs: dict = {}
        if sys.platform == "win32":
            # CREATE_NO_WINDOW, not DETACHED_PROCESS: the latter is known to
            # pop up an empty console window (https://bugs.python.org/issue41619).
            creationflags = (
                subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            kwargs["start_new_session"] = True

        return subprocess.Popen(
            [sys.executable, "-m", "tasks_mcp.web"],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creationflags,
            **kwargs,
        )
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[tasks-mcp] web autostart failed: {exc}", file=sys.stderr)
        return None

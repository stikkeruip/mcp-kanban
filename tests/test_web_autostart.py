"""Autostart tests: spawn-if-absent, skip-if-present."""

import json
import socket
import time
import urllib.request

import pytest

from tasks_mcp.config import AppConfig
from tasks_mcp.web.autostart import ensure_web_running


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_does_not_spawn_when_port_is_taken(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        cfg = AppConfig(
            db_path=tmp_path / "t.db",
            transition_policy="free",
            web_host="127.0.0.1",
            web_port=port,
        )
        assert ensure_web_running(cfg) is None


def test_spawns_a_working_web_server(tmp_path):
    cfg = AppConfig(
        db_path=tmp_path / "t.db",
        transition_policy="free",
        web_host="127.0.0.1",
        web_port=free_port(),
    )
    proc = ensure_web_running(cfg)
    assert proc is not None
    try:
        deadline = time.monotonic() + 15
        board = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://{cfg.web_host}:{cfg.web_port}/api/board", timeout=1
                ) as res:
                    board = json.loads(res.read())
                break
            except OSError:
                time.sleep(0.2)
        if board is None:
            pytest.fail("spawned web server never came up")
        assert [c["status"] for c in board["columns"]] == [
            "backlog",
            "in_progress",
            "testing",
            "done",
        ]
        # second call must detect it and not spawn again
        assert ensure_web_running(cfg) is None
    finally:
        proc.kill()
        proc.wait(timeout=10)

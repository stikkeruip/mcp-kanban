"""Web adapter tests: a live threaded server exercised over real HTTP."""

import json
import threading
import urllib.request
from urllib.error import HTTPError

import pytest

from tasks_mcp.config import AppConfig
from tasks_mcp.web.server import build_httpd


@pytest.fixture
def base_url(tmp_path):
    cfg = AppConfig(
        db_path=tmp_path / "tasks.db",
        transition_policy="free",
        web_host="127.0.0.1",
        web_port=0,  # let the OS pick a free port
    )
    httpd = build_httpd(cfg)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    yield f"http://{host}:{port}"
    httpd.shutdown()
    httpd.server_close()


def request(method: str, url: str, body: dict | None = None):
    """Return (status, parsed JSON) without raising on 4xx."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.loads(res.read())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


def add(base_url, title="task", **extra):
    status, task = request("POST", f"{base_url}/api/tasks", {"title": title, **extra})
    assert status == 201
    return task


class TestStaticPage:
    def test_index_is_served(self, base_url):
        with urllib.request.urlopen(base_url + "/") as res:
            html = res.read().decode()
        assert res.headers["Content-Type"].startswith("text/html")
        assert 'id="board"' in html


class TestApi:
    def test_add_lands_in_backlog(self, base_url):
        task = add(base_url, "Buy milk", priority="high", tags=["errand"])
        assert task["status"] == "backlog"
        assert task["priority"] == "high"
        assert task["tags"] == ["errand"]

    def test_board_has_four_columns_in_order(self, base_url):
        status, board = request("GET", f"{base_url}/api/board")
        assert status == 200
        assert [c["status"] for c in board["columns"]] == [
            "backlog",
            "in_progress",
            "testing",
            "done",
        ]

    def test_move_shows_up_on_board(self, base_url):
        task = add(base_url)
        status, moved = request(
            "POST",
            f"{base_url}/api/tasks/{task['id']}/move",
            {"target_status": "testing"},
        )
        assert status == 200 and moved["status"] == "testing"
        _, board = request("GET", f"{base_url}/api/board")
        by_status = {c["status"]: c["tasks"] for c in board["columns"]}
        assert [t["id"] for t in by_status["testing"]] == [task["id"]]

    def test_patch_edits_fields(self, base_url):
        task = add(base_url, "old", description="keep me")
        status, edited = request(
            "PATCH", f"{base_url}/api/tasks/{task['id']}", {"title": "new"}
        )
        assert status == 200
        assert edited["title"] == "new"
        assert edited["description"] == "keep me"

    def test_archive_hides_from_default_list(self, base_url):
        task = add(base_url)
        status, archived = request(
            "POST", f"{base_url}/api/tasks/{task['id']}/archive"
        )
        assert status == 200 and archived["archived"] is True
        _, visible = request("GET", f"{base_url}/api/tasks")
        assert visible == []
        _, everything = request("GET", f"{base_url}/api/tasks?include_archived=true")
        assert [t["id"] for t in everything] == [task["id"]]

    def test_list_filters(self, base_url):
        add(base_url, "a", tags=["home"])
        b = add(base_url, "b", priority="high")
        _, high = request("GET", f"{base_url}/api/tasks?priority=high")
        assert [t["id"] for t in high] == [b["id"]]
        _, home = request("GET", f"{base_url}/api/tasks?tag=home")
        assert [t["title"] for t in home] == ["a"]


class TestErrorMapping:
    def test_missing_task_is_404(self, base_url):
        status, body = request("GET", f"{base_url}/api/tasks/999")
        assert status == 404
        assert "no task with id 999" in body["error"]

    def test_validation_error_is_400(self, base_url):
        status, body = request("POST", f"{base_url}/api/tasks", {"title": "   "})
        assert status == 400
        assert "title" in body["error"]

    def test_bad_target_status_is_400(self, base_url):
        task = add(base_url)
        status, body = request(
            "POST",
            f"{base_url}/api/tasks/{task['id']}/move",
            {"target_status": "shipped"},
        )
        assert status == 400
        assert "invalid status" in body["error"]

    def test_unknown_endpoint_is_404(self, base_url):
        status, _ = request("GET", f"{base_url}/api/nope")
        assert status == 404

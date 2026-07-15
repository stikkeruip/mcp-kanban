"""Web view: JSON API + static board page over ``TaskService``.

Endpoints mirror the MCP tools one-to-one:

    GET    /                        the board UI (static/index.html)
    GET    /api/board               get_board
    GET    /api/tasks               list_tasks (?status=&tag=&priority=&include_archived=true)
    POST   /api/tasks               add_task        {title, description?, priority?, tags?}
    GET    /api/tasks/{id}          get_task
    PATCH  /api/tasks/{id}          edit_task       {title?, description?, priority?, tags?}
    POST   /api/tasks/{id}/move     move_task       {target_status}
    POST   /api/tasks/{id}/archive  archive_task

Service exceptions map to HTTP: TaskNotFound → 404, ValidationError → 400,
InvalidTransition → 409. Built on the stdlib ``http.server`` — a personal
board does not need a web framework, and this keeps the project at a
single runtime dependency.
"""

from __future__ import annotations

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from tasks_mcp.config import AppConfig, load_config
from tasks_mcp.domain.task import Task
from tasks_mcp.services.errors import (
    InvalidTransition,
    TaskNotFound,
    ValidationError,
)
from tasks_mcp.services.task_service import TaskService
from tasks_mcp.wiring import build_service

_STATIC_DIR = Path(__file__).parent / "static"

_TASK_ROUTE = re.compile(r"^/api/tasks/(\d+)$")
_MOVE_ROUTE = re.compile(r"^/api/tasks/(\d+)/move$")
_ARCHIVE_ROUTE = re.compile(r"^/api/tasks/(\d+)/archive$")
_RESUME_ROUTE = re.compile(r"^/api/tasks/(\d+)/resume$")

# Cross-site defense: browsers let any webpage POST to 127.0.0.1, and a
# "launch a terminal" endpoint must not be reachable that way. Requiring a
# custom header forces a CORS preflight for cross-origin callers, which
# this server never approves. Our own UI sends the header on every call.
_GUARD_HEADER = "X-Tasks-MCP"

# Re-exported under the old names: tests and the handler use these, and the
# implementation now lives in tasks_mcp.resume (shared with the MCP tool).
from tasks_mcp.resume import launch_terminal as _launch_terminal  # noqa: E402
from tasks_mcp.resume import parse_resume_link  # noqa: E402, F401


def task_to_dict(task: Task) -> dict:
    """Format a domain Task as a JSON-ready dict.

    Deliberately duplicated from the MCP adapter (10 lines): each adapter
    owns its own presentation, so either can be deleted or reshaped without
    touching the other.
    """
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


class KanbanRequestHandler(BaseHTTPRequestHandler):
    """Routes HTTP requests to TaskService calls. No business logic."""

    service: TaskService  # injected by build_handler()
    protocol_version = "HTTP/1.1"

    # -- verb entry points ------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        self._dispatch(self._get_routes)

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch(self._post_routes)

    def do_PATCH(self) -> None:  # noqa: N802
        self._dispatch(self._patch_routes)

    # -- routing -----------------------------------------------------------

    def _dispatch(self, router) -> None:
        try:
            router()
        except TaskNotFound as exc:
            self._json(404, {"error": str(exc)})
        except ValidationError as exc:
            self._json(400, {"error": str(exc)})
        except InvalidTransition as exc:
            self._json(409, {"error": str(exc)})
        except json.JSONDecodeError:
            self._json(400, {"error": "request body is not valid JSON"})

    def _get_routes(self) -> None:
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            self._html((_STATIC_DIR / "index.html").read_bytes())
            return
        if url.path == "/api/board":
            self._json(200, self._board())
            return
        if url.path == "/api/tasks":
            query = parse_qs(url.query)
            tasks = self.service.list_tasks(
                status=self._one(query, "status"),
                tag=self._one(query, "tag"),
                priority=self._one(query, "priority"),
                include_archived=self._one(query, "include_archived")
                in ("1", "true", "yes"),
            )
            self._json(200, [task_to_dict(t) for t in tasks])
            return
        match = _TASK_ROUTE.match(url.path)
        if match:
            self._json(200, task_to_dict(self.service.get_task(int(match.group(1)))))
            return
        self._json(404, {"error": f"no such endpoint: GET {url.path}"})

    def _post_routes(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/tasks":
            body = self._body()
            task = self.service.add_task(
                body.get("title"),
                description=body.get("description"),
                priority=body.get("priority", "normal"),
                tags=body.get("tags"),
                link=body.get("link"),
            )
            self._json(201, task_to_dict(task))
            return
        match = _MOVE_ROUTE.match(path)
        if match:
            body = self._body()
            task = self.service.move_task(
                int(match.group(1)), body.get("target_status")
            )
            self._json(200, task_to_dict(task))
            return
        match = _ARCHIVE_ROUTE.match(path)
        if match:
            self._json(200, task_to_dict(self.service.archive_task(int(match.group(1)))))
            return
        match = _RESUME_ROUTE.match(path)
        if match:
            self._resume(int(match.group(1)))
            return
        self._json(404, {"error": f"no such endpoint: POST {path}"})

    def _resume(self, task_id: int) -> None:
        """Open a terminal resuming the Claude Code session in a task's link."""
        if self.headers.get(_GUARD_HEADER) != "1":
            self._json(403, {"error": f"missing {_GUARD_HEADER} header"})
            return
        task = self.service.get_task(task_id)
        parsed = parse_resume_link(task.link)
        if parsed is None:
            self._json(
                400,
                {
                    "error": "task's link is not a resume command "
                    '(expected "cd <dir>; claude -r <session-id>")'
                },
            )
            return
        directory, session_id = parsed
        _launch_terminal(directory, session_id)
        self._json(200, {"launched": True, "directory": directory, "session_id": session_id})

    def _patch_routes(self) -> None:
        path = urlparse(self.path).path
        match = _TASK_ROUTE.match(path)
        if match:
            body = self._body()
            task = self.service.edit_task(
                int(match.group(1)),
                title=body.get("title"),
                description=body.get("description"),
                priority=body.get("priority"),
                tags=body.get("tags"),
                link=body.get("link"),
            )
            self._json(200, task_to_dict(task))
            return
        self._json(404, {"error": f"no such endpoint: PATCH {path}"})

    # -- helpers -----------------------------------------------------------

    def _board(self) -> dict:
        board = self.service.get_board()
        return {
            "columns": [
                {
                    "status": column["status"].value,
                    "tasks": [task_to_dict(t) for t in column["tasks"]],
                }
                for column in board["columns"]
            ]
        }

    @staticmethod
    def _one(query: dict, key: str) -> str | None:
        values = query.get(key)
        return values[0] if values else None

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        data = json.loads(raw or b"{}")
        if not isinstance(data, dict):
            raise ValidationError("request body must be a JSON object")
        return data

    def _json(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        """Quiet default request logging down to stderr one-liners."""
        print(f"[web] {self.address_string()} {format % args}", file=sys.stderr)


def build_handler(service: TaskService) -> type[KanbanRequestHandler]:
    """Bind a service instance into a request handler class."""

    class Handler(KanbanRequestHandler):
        pass

    Handler.service = service
    return Handler


def build_httpd(config: AppConfig) -> ThreadingHTTPServer:
    """Wire the object graph and return a ready-to-serve HTTP server."""
    service = build_service(config)
    return ThreadingHTTPServer(
        (config.web_host, config.web_port), build_handler(service)
    )


def main() -> None:
    """Entry point (``tasks-mcp-web`` script)."""
    cfg = load_config()
    httpd = build_httpd(cfg)
    host, port = httpd.server_address[:2]
    print(f"tasks-mcp web view on http://{host}:{port}", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

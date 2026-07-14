"""Phase 4 smoke tests: the wired server, exercised through an in-memory
MCP client — the same protocol path Claude uses, minus the transport."""

import asyncio
import json

import pytest
from fastmcp import Client

from tasks_mcp.config import AppConfig
from tasks_mcp.mcp.server import build_server
from tasks_mcp.wiring import build_policy

EXPECTED_TOOLS = {
    "add_task",
    "list_tasks",
    "get_task",
    "edit_task",
    "move_task",
    "archive_task",
    "get_board",
}


def make_server(tmp_path):
    cfg = AppConfig(db_path=tmp_path / "tasks.db", transition_policy="free")
    return build_server(cfg)


def call(server, tool, args=None):
    """Call one tool through the MCP client and return its JSON payload."""

    async def run():
        async with Client(server) as client:
            result = await client.call_tool(tool, args or {})
            data = getattr(result, "data", None)
            if data is not None:
                return data
            return json.loads(result.content[0].text)

    return asyncio.run(run())


def test_unknown_transition_policy_is_refused():
    with pytest.raises(ValueError, match="unknown transition policy"):
        build_policy("chaotic")


def test_all_seven_tools_are_registered(tmp_path):
    async def run():
        async with Client(make_server(tmp_path)) as client:
            return {tool.name for tool in await client.list_tools()}

    assert asyncio.run(run()) == EXPECTED_TOOLS


def test_full_flow_through_the_protocol(tmp_path):
    server = make_server(tmp_path)

    created = call(
        server,
        "add_task",
        {"title": "Ship v1", "priority": "high", "tags": ["mcp"]},
    )
    assert created["status"] == "backlog"
    task_id = created["id"]

    moved = call(server, "move_task", {"task_id": task_id, "target_status": "testing"})
    assert moved["status"] == "testing"

    edited = call(server, "edit_task", {"task_id": task_id, "description": "almost"})
    assert edited["description"] == "almost"

    board = call(server, "get_board")
    assert [c["status"] for c in board["columns"]] == [
        "backlog",
        "in_progress",
        "testing",
        "done",
    ]
    assert board["columns"][2]["tasks"][0]["id"] == task_id

    call(server, "archive_task", {"task_id": task_id})
    assert call(server, "list_tasks") == []
    assert call(server, "list_tasks", {"include_archived": True})[0]["id"] == task_id


def test_service_errors_surface_as_clean_tool_errors(tmp_path):
    server = make_server(tmp_path)
    with pytest.raises(Exception, match="no task with id 999"):
        call(server, "move_task", {"task_id": 999, "target_status": "done"})
    with pytest.raises(Exception, match="invalid status"):
        call(server, "move_task", {"task_id": 999, "target_status": "shipped"})


def test_database_persists_across_server_instances(tmp_path):
    call(make_server(tmp_path), "add_task", {"title": "durable"})
    tasks = call(make_server(tmp_path), "list_tasks")
    assert [t["title"] for t in tasks] == ["durable"]

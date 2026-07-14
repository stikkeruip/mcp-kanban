# tasks-mcp

A personal kanban board as a local MCP server, backed by SQLite. Four columns — `backlog → in_progress → testing → done` — driven entirely through typed MCP tools: Claude pulls your tasks, adds new ones, edits them, and moves them across the board.

Tasks are never hard-deleted: archiving hides a task from listings but keeps it in the database.

## Requirements

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) (recommended, not required — see the venv option below)

## Install & run

### Option A: uv (recommended)

From this directory:

```bash
uv run tasks-mcp
```

That resolves the environment, installs the single runtime dependency (`fastmcp`), and serves over stdio — uv even downloads a suitable Python if the machine has none. It is also exactly what an MCP host runs for you (see below).

Install uv itself with `winget install --id=astral-sh.uv -e` (Windows) or `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux).

### Option B: plain venv (no uv)

```powershell
# Windows
py -3.13 -m venv .venv
.venv\Scripts\pip install -e .
```

```bash
# macOS/Linux
python3 -m venv .venv
.venv/bin/pip install -e .
```

The server is then the `tasks-mcp` entry point inside the venv (`.venv\Scripts\tasks-mcp.exe` on Windows, `.venv/bin/tasks-mcp` elsewhere). Re-run the `pip install` step after pulling dependency changes.

## Registering with Claude Desktop / Cowork

Add to `claude_desktop_config.json` (Windows: `%AppData%\Claude\`, macOS: `~/Library/Application Support/Claude/`):

```json
{
  "mcpServers": {
    "tasks": {
      "command": "uv",
      "args": ["--directory", "C:\\dev\\mcp-kanban", "run", "tasks-mcp"]
    }
  }
}
```

On macOS/Linux use the absolute path to this folder in `--directory`. If `uv` is not on the host's PATH, use the full path to the executable (`where uv` / `which uv`). Restart the Claude app fully after saving.

If you went with the venv install (Option B), point the config straight at the entry point instead — no `args` needed:

```json
{
  "mcpServers": {
    "tasks": {
      "command": "C:\\dev\\mcp-kanban\\.venv\\Scripts\\tasks-mcp.exe"
    }
  }
}
```

(macOS/Linux: `"command": "/path/to/mcp-kanban/.venv/bin/tasks-mcp"`.)

Then try: *"add a task to buy milk"*, *"show my board"*, *"move it to testing"*.

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `TASKS_MCP_DB` | `~/.local/share/tasks-mcp/tasks.db` | SQLite database path (parent dir is created) |
| `TASKS_MCP_TRANSITIONS` | `free` | Transition policy. `free` = any column to any column. Hook for a future `linear` policy. |

Set them via the `env` key of the MCP config entry if you want a non-default location.

## Tools

| Tool | What it does |
|---|---|
| `add_task` | Create a task (lands in `backlog`). Title required; optional description, priority (`low`/`normal`/`high`), tags. |
| `list_tasks` | List tasks with optional AND-combined filters: status, tag, priority, `include_archived`. |
| `get_task` | Full detail of one task by id (works for archived tasks). |
| `edit_task` | Update title/description/priority/tags. Omitted fields keep their value; empty-string description clears it. |
| `move_task` | Move a task to another column — the kanban action. |
| `archive_task` | Soft delete. No hard delete exists. |
| `get_board` | The whole board grouped by column; always all four columns, in order. |

## Architecture

Dependencies point inward: `mcp → services → storage(interface) + domain`.

```
src/tasks_mcp/
├── domain/       # pure data + rules, zero I/O (Task, Status, Priority, TransitionPolicy)
├── storage/      # TaskRepository interface, SQLite impl, versioned migration runner
├── services/     # TaskService — all business logic, typed exceptions
├── mcp/          # thin, disposable adapter: tools + composition root
└── config.py     # env resolution in one place
```

Design decisions worth knowing:

- **Storage is swappable.** The service layer codes against the abstract `TaskRepository`; the SQLite implementation (raw SQL, no ORM) is the only file that knows how a task is stored. WAL mode is on, so a future read-only consumer (e.g. an HTML board view) can read while the server writes.
- **Schema changes are migrations.** A versioned runner applies `NNN_*.sql` files in order, each in its own transaction, on every startup. Adding a field later = dropping a new `002_*.sql` file next to `001_initial.sql`. Never a manual `ALTER`.
- **Transitions are a policy object.** v1 ships `FreeTransitionPolicy`. A strict linear pipeline is a new class registered in `mcp/server.py` and selected via `TASKS_MCP_TRANSITIONS` — zero changes to existing code.
- **The MCP layer is disposable.** Tools parse input, call one service method, format output. Replacing MCP with a CLI or web app touches nothing beneath `mcp/`.

## Development

```bash
uv sync                # create venv with dev deps
uv run pytest          # 71 tests: domain, storage, services, MCP protocol smoke
```

The service tests run against an in-memory SQLite repository; the MCP tests exercise the wired server through an in-memory MCP client — the same protocol path a real host uses.

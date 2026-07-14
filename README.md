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

The `tasks-mcp` / `tasks-mcp-web` console scripts exist too, but prefer the `python -m tasks_mcp` / `python -m tasks_mcp.web` module form for anything long-running: Windows locks a running `.exe`, which blocks `uv run` from refreshing the environment while a server is up.

To install uv itself, see the [official installation guide](https://docs.astral.sh/uv/getting-started/installation/).

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
      "args": ["--directory", "C:\\dev\\mcp-kanban", "run", "python", "-m", "tasks_mcp"]
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
| `TASKS_MCP_WEB_HOST` | `127.0.0.1` | Bind address for the web view. |
| `TASKS_MCP_WEB_PORT` | `8765` | Port for the web view. |
| `TASKS_MCP_WEB_AUTOSTART` | `1` | MCP sessions spawn the web view if it isn't running. `0` to disable. |

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

## Web view (drag & drop board)

A browser UI over the same database, runnable alongside the MCP server (WAL mode makes concurrent access safe).

**It starts itself:** whenever an MCP session launches (Claude Desktop, Claude Code, ...), it checks the web port and spawns the board in the background if nothing is listening — whichever session comes first starts it, the rest find it running. Every MCP host process is independent, but they all share the database and this one web view. Set `TASKS_MCP_WEB_AUTOSTART=0` to opt out. It keeps running after sessions close; stop it by killing the `python -m tasks_mcp.web` process.

To run it manually instead:

```bash
uv run python -m tasks_mcp.web        # or .venv\Scripts\python -m tasks_mcp.web with the venv install
```

Then open <http://127.0.0.1:8765>. Drag cards between columns to move them, click a card to edit or archive it, add tasks from the header. The page polls every few seconds, so changes Claude makes through MCP appear on their own.

It exposes the same seven operations as JSON endpoints (`/api/board`, `/api/tasks`, `/api/tasks/{id}`, `/api/tasks/{id}/move`, `/api/tasks/{id}/archive`) and is built on the stdlib HTTP server — no new dependencies, no build step. Binds to localhost only by default (`TASKS_MCP_WEB_HOST` / `TASKS_MCP_WEB_PORT` to change).

## Architecture

Dependencies point inward: `mcp → services → storage(interface) + domain`.

```
src/tasks_mcp/
├── domain/       # pure data + rules, zero I/O (Task, Status, Priority, TransitionPolicy)
├── storage/      # TaskRepository interface, SQLite impl, versioned migration runner
├── services/     # TaskService — all business logic, typed exceptions
├── mcp/          # thin, disposable adapter: MCP tools
├── web/          # thin, disposable adapter: JSON API + drag-and-drop board UI
├── wiring.py     # shared composition: config → service object graph
└── config.py     # env resolution in one place
```

Design decisions worth knowing:

- **Storage is swappable.** The service layer codes against the abstract `TaskRepository`; the SQLite implementation (raw SQL, no ORM) is the only file that knows how a task is stored. WAL mode is on, so a future read-only consumer (e.g. an HTML board view) can read while the server writes.
- **Schema changes are migrations.** A versioned runner applies `NNN_*.sql` files in order, each in its own transaction, on every startup. Adding a field later = dropping a new `002_*.sql` file next to `001_initial.sql`. Never a manual `ALTER`.
- **Transitions are a policy object.** v1 ships `FreeTransitionPolicy`. A strict linear pipeline is a new class registered in `mcp/server.py` and selected via `TASKS_MCP_TRANSITIONS` — zero changes to existing code.
- **Adapters are disposable.** MCP tools and web endpoints alike parse input, call one service method, format output. The web view was added without touching a line beneath the adapter layer — the proof the seams work.

## Development

```bash
uv sync                # create venv with dev deps
uv run pytest          # domain, storage, services, MCP protocol, web API
```

The service tests run against an in-memory SQLite repository; the MCP tests exercise the wired server through an in-memory MCP client; the web tests hit a live threaded server over real HTTP.

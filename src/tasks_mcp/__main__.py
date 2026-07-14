"""``python -m tasks_mcp`` — run the MCP server over stdio.

Preferred over the ``tasks-mcp`` console script for long-running use on
Windows: a running ``.exe`` launcher is locked by the OS, which blocks
``uv run`` from re-syncing the environment. ``python -m`` keeps the
launchers free to be replaced.
"""

from tasks_mcp.mcp.server import main

if __name__ == "__main__":
    main()

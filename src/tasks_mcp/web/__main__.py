"""``python -m tasks_mcp.web`` — run the browser board.

Preferred over the ``tasks-mcp-web`` console script for long-running use
on Windows (see ``tasks_mcp.__main__`` for why).
"""

from tasks_mcp.web.server import main

if __name__ == "__main__":
    main()

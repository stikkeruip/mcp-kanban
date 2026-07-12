"""tasks-mcp: a personal kanban board exposed as a local MCP server.

Layering (dependencies point inward, never outward):

    mcp  ->  services  ->  storage (interface) + domain

``domain`` imports nothing from the project. ``storage`` depends only on
``domain``. ``services`` depends on ``domain`` and the abstract
``TaskRepository`` — never on a concrete database. ``mcp`` is a thin,
disposable adapter over ``services``.
"""

__version__ = "0.1.0"

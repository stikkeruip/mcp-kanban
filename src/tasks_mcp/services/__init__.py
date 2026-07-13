"""Business logic — the real internal API.

Every consumer (MCP today; CLI or web view later) calls ``TaskService``.
It depends only on the ``TaskRepository`` interface and a
``TransitionPolicy``, both injected — never on a concrete database.
"""

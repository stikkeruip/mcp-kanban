"""THIN, disposable web adapter — the second consumer of ``TaskService``.

A stdlib HTTP server exposing the same seven operations as the MCP tools,
plus a single-page drag-and-drop board UI. Runs as its own process; WAL
mode on the database lets it operate alongside the MCP server. Zero
business logic and zero new dependencies live here.
"""

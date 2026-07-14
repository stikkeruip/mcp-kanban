"""THIN, disposable MCP adapter.

Each tool parses input, calls one ``TaskService`` method, formats the
result. Zero business logic. This whole package could be deleted and
replaced (CLI, web app, another transport) without touching anything
beneath it.
"""

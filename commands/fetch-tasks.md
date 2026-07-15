---
description: Show kanban tasks, optionally filtered (status, tag, priority)
argument-hint: "[backlog|in_progress|testing|done] [tag:<tag>] [priority:low|normal|high] [archived]"
---

Fetch tasks from the personal kanban board (tasks MCP server) and display them. Follow these rules exactly — no interpretation beyond them:

1. Parse `$ARGUMENTS` deterministically, token by token:
   - a bare word equal to `backlog`, `in_progress`, `testing`, or `done` → status filter
   - `tag:<value>` → tag filter
   - `priority:<value>` → priority filter
   - `archived` → include archived tasks
   - any other token → report it as an unrecognized argument and stop; do not guess
2. If there are no arguments, call `get_board` and render all four columns in order.
3. If there are filters, call `list_tasks` with exactly those filters.
4. Output: a compact table with columns id, title, status, priority, tags — mark tasks that have a link with `⧉` after the title. End with a one-line count. No other commentary.

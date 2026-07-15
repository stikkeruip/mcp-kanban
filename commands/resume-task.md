---
description: Resume the Claude Code chat linked to a kanban task (interactive picker)
argument-hint: "[task id or title keyword]"
---

Resume a parked Claude Code chat via the tasks MCP `resume_task` tool.

- If `$ARGUMENTS` is a number, call `resume_task` with that `task_id`.
- If `$ARGUMENTS` is a keyword, call `list_tasks`, find tasks whose title matches it (case-insensitive) and whose link looks like a resume command (`cd <dir>; claude -r <id>`). Exactly one match → call `resume_task` with its id. Zero or several → show them and stop.
- If `$ARGUMENTS` is empty, call `resume_task` with no arguments — it presents an interactive picker.

The tool opens a new terminal window with the resumed chat (it must run in the task's original directory, which the tool handles). Afterwards confirm with the task title and session id — the current session stays as it is; the resumed chat lives in the new terminal. Nothing else.

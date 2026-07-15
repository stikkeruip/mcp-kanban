---
description: Add a task to the kanban board (deterministic flags, or a sentence for the AI)
argument-hint: "\"<title>\" [--high|--low] [--tag <tag>]... [--desc \"<text>\"] [--link] | <sentence>"
---

Session id for --link: !`cat .claude/last-session-id 2>/dev/null || echo "(missing)"`
Project directory: !`pwd`

Create exactly ONE task on the personal kanban board (tasks MCP `add_task`) from `$ARGUMENTS`.

Mode selection:

**Deterministic mode** — if `$ARGUMENTS` contains any `--` flag or begins with a quoted string, apply it literally:
- the quoted string is the title, verbatim
- `--high` / `--low` → priority (default normal)
- `--tag <value>` (repeatable) → tags
- `--desc "<text>"` → description
- `--link` → set link to exactly: `cd <project directory above>; claude -r <session id above>`. If the session id shows "(missing)", say the SessionStart hook isn't set up and create the task without a link.
- an unrecognized flag → report it and stop; do not guess

**AI mode** — otherwise, treat `$ARGUMENTS` as a natural-language request: extract a concise title, put remaining detail in the description, and set priority/tags only when explicitly implied. If the request mentions continuing/resuming this conversation, attach the link as in `--link`.

After creating, confirm with the task id and a one-line summary. Nothing else.

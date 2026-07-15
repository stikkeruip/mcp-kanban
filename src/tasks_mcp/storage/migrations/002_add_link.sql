-- Optional free-text link on a task: a URL or command that reopens the
-- context the task came from (e.g. "cd C:\proj; claude -r <session-id>"
-- to resume a parked Claude Code chat).
ALTER TABLE tasks ADD COLUMN link TEXT;

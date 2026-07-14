CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    description  TEXT,
    status       TEXT NOT NULL DEFAULT 'backlog'
                 CHECK (status IN ('backlog','in_progress','testing','done')),
    priority     TEXT NOT NULL DEFAULT 'normal'
                 CHECK (priority IN ('low','normal','high')),
    tags         TEXT NOT NULL DEFAULT '[]',   -- JSON array
    created_at   TEXT NOT NULL,                -- ISO 8601
    updated_at   TEXT NOT NULL,
    archived     INTEGER NOT NULL DEFAULT 0    -- 0/1
);

CREATE INDEX IF NOT EXISTS idx_tasks_status   ON tasks(status)   WHERE archived = 0;
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority) WHERE archived = 0;

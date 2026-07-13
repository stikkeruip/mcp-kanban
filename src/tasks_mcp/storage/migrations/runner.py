"""Versioned SQL migration runner.

Maintains a single-row ``schema_version`` table. On :func:`run_migrations`,
every ``NNN_*.sql`` file in this directory with a number greater than the
current version is applied in order, each inside its own transaction,
bumping the version as it goes. Idempotent — safe to run on every launch.

Adding a field later is a 30-second job: drop ``002_add_whatever.sql`` next
to this file and restart. No manual DB surgery, no risk to existing data.

Expects a connection in autocommit mode (``isolation_level=None``) so it can
manage transactions explicitly; :func:`tasks_mcp.storage.sqlite_repository.connect`
provides one.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from tasks_mcp.storage.errors import MigrationError

MIGRATIONS_DIR = Path(__file__).parent
_MIGRATION_FILE = re.compile(r"^(\d{3})_.+\.sql$")


def get_version(conn: sqlite3.Connection) -> int:
    """Return the current schema version, creating the tracking table at 0 if absent."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
    )
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (0)")
        return 0
    return int(row[0])


def discover_migrations(directory: Path = MIGRATIONS_DIR) -> list[tuple[int, Path]]:
    """Return all migration files as ``(number, path)``, sorted ascending.

    Raises ``MigrationError`` on duplicate numbers — two files claiming the
    same version is always a mistake.
    """
    found: dict[int, Path] = {}
    for path in sorted(directory.iterdir()):
        match = _MIGRATION_FILE.match(path.name)
        if not match:
            continue
        number = int(match.group(1))
        if number in found:
            raise MigrationError(
                f"duplicate migration number {number:03d}: "
                f"{found[number].name} and {path.name}"
            )
        found[number] = path
    return sorted(found.items())


def _statements(script: str):
    """Split a SQL script into complete statements.

    Uses ``sqlite3.complete_statement`` so semicolons inside string literals
    do not split a statement.
    """
    buffer = ""
    for chunk in script.split(";"):
        buffer += chunk + ";"
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            buffer = ""
            if statement and statement != ";":
                yield statement


def run_migrations(
    conn: sqlite3.Connection, directory: Path = MIGRATIONS_DIR
) -> int:
    """Apply every pending migration in order; return the resulting version.

    Each migration runs in its own transaction together with its version
    bump: a failing migration rolls back completely and leaves the recorded
    version untouched. Gaps in the numbering are refused.
    """
    current = get_version(conn)
    for number, path in discover_migrations(directory):
        if number <= current:
            continue
        if number != current + 1:
            raise MigrationError(
                f"migration gap: at version {current}, "
                f"next file is {path.name} (expected {current + 1:03d}_*.sql)"
            )
        script = path.read_text(encoding="utf-8")
        try:
            conn.execute("BEGIN")
            for statement in _statements(script):
                conn.execute(statement)
            conn.execute("UPDATE schema_version SET version = ?", (number,))
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            conn.execute("ROLLBACK")
            raise MigrationError(f"migration {path.name} failed: {exc}") from exc
        current = number
    return current

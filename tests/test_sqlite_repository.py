"""Phase 2 tests: migration runner and the concrete SQLite repository."""

import sqlite3
from datetime import datetime, timezone

import pytest

from tasks_mcp.domain.task import Priority, Status, Task
from tasks_mcp.storage.errors import MigrationError, RowNotFound, StorageError
from tasks_mcp.storage.migrations.runner import get_version, run_migrations
from tasks_mcp.storage.sqlite_repository import SqliteTaskRepository, connect

NOW = datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc)


def make_task(**overrides) -> Task:
    defaults = dict(
        id=None,
        title="Write tests",
        description="Cover the storage layer",
        status=Status.BACKLOG,
        priority=Priority.NORMAL,
        tags=["dev", "kanban"],
        created_at=NOW,
        updated_at=NOW,
        archived=False,
    )
    defaults.update(overrides)
    return Task(**defaults)


@pytest.fixture
def conn():
    conn = connect(":memory:")
    run_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture
def repo(conn):
    return SqliteTaskRepository(conn)


class TestMigrations:
    def test_fresh_db_migrates_to_version_1(self):
        conn = connect(":memory:")
        assert run_migrations(conn) == 1
        assert get_version(conn) == 1

    def test_rerun_is_idempotent(self, conn):
        assert run_migrations(conn) == 1
        assert run_migrations(conn) == 1

    def test_tasks_table_and_indexes_exist(self, conn):
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'index')"
            )
        }
        assert "tasks" in names
        assert "idx_tasks_status" in names
        assert "idx_tasks_priority" in names

    def test_gap_in_numbering_is_refused(self, tmp_path):
        (tmp_path / "001_a.sql").write_text("CREATE TABLE a (x);")
        (tmp_path / "003_c.sql").write_text("CREATE TABLE c (x);")
        conn = connect(":memory:")
        with pytest.raises(MigrationError, match="gap"):
            run_migrations(conn, tmp_path)
        # 001 was still applied atomically before the gap was detected.
        assert get_version(conn) == 1

    def test_failed_migration_rolls_back_completely(self, tmp_path):
        (tmp_path / "001_bad.sql").write_text(
            "CREATE TABLE good (x);\nCREATE TABLE bad (syntax error here;"
        )
        conn = connect(":memory:")
        with pytest.raises(MigrationError):
            run_migrations(conn, tmp_path)
        assert get_version(conn) == 0
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "good" not in tables

    def test_check_constraint_refuses_a_fifth_status(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO tasks (title, status, priority, tags, created_at, updated_at)"
                " VALUES ('x', 'shipped', 'normal', '[]', '2026-01-01', '2026-01-01')"
            )


class TestRoundTrip:
    def test_add_assigns_id_and_get_returns_equal_task(self, repo):
        stored = repo.add(make_task())
        assert stored.id is not None
        fetched = repo.get(stored.id)
        assert fetched == stored

    def test_tags_survive_serialization(self, repo):
        stored = repo.add(make_task(tags=["a b", "c/d", "unicode-ø"]))
        assert repo.get(stored.id).tags == ["a b", "c/d", "unicode-ø"]

    def test_datetimes_round_trip_timezone_aware(self, repo):
        fetched = repo.get(repo.add(make_task()).id)
        assert fetched.created_at == NOW
        assert fetched.created_at.tzinfo is not None

    def test_archived_round_trips_as_bool(self, repo):
        fetched = repo.get(repo.add(make_task(archived=True)).id)
        assert fetched.archived is True

    def test_get_missing_returns_none(self, repo):
        assert repo.get(999) is None

    def test_add_with_preassigned_id_is_refused(self, repo):
        with pytest.raises(StorageError):
            repo.add(make_task(id=7))


class TestUpdate:
    def test_update_persists_all_mutable_fields(self, repo):
        task = repo.add(make_task())
        task.title = "New title"
        task.status = Status.TESTING
        task.priority = Priority.HIGH
        task.tags = ["changed"]
        repo.update(task)
        fetched = repo.get(task.id)
        assert fetched.title == "New title"
        assert fetched.status is Status.TESTING
        assert fetched.priority is Priority.HIGH
        assert fetched.tags == ["changed"]

    def test_update_missing_row_raises(self, repo):
        with pytest.raises(RowNotFound):
            repo.update(make_task(id=999))

    def test_update_without_id_raises(self, repo):
        with pytest.raises(StorageError):
            repo.update(make_task(id=None))


class TestArchiveAndList:
    def test_archive_flips_flag_and_returns_task(self, repo):
        task = repo.add(make_task())
        archived = repo.archive(task.id)
        assert archived.archived is True

    def test_archive_missing_returns_none(self, repo):
        assert repo.archive(999) is None

    def test_archived_hidden_by_default_but_still_fetchable(self, repo):
        task = repo.add(make_task())
        repo.archive(task.id)
        assert repo.list() == []
        assert repo.list(include_archived=True)[0].id == task.id
        assert repo.get(task.id) is not None

    def test_list_filters_by_status_priority_and_tag(self, repo):
        a = repo.add(make_task(title="a", status=Status.BACKLOG, tags=["home"]))
        b = repo.add(
            make_task(
                title="b",
                status=Status.TESTING,
                priority=Priority.HIGH,
                tags=["work"],
            )
        )
        assert [t.id for t in repo.list(status=Status.TESTING)] == [b.id]
        assert [t.id for t in repo.list(priority=Priority.HIGH)] == [b.id]
        assert [t.id for t in repo.list(tag="home")] == [a.id]
        assert [t.id for t in repo.list(status=Status.BACKLOG, tag="work")] == []

    def test_tag_filter_is_exact_not_substring(self, repo):
        repo.add(make_task(tags=["homework"]))
        assert repo.list(tag="home") == []

    def test_list_returns_oldest_first(self, repo):
        first = repo.add(make_task(title="first"))
        second = repo.add(make_task(title="second"))
        assert [t.id for t in repo.list()] == [first.id, second.id]

    def test_wal_mode_is_enabled_on_file_databases(self, tmp_path):
        conn = connect(tmp_path / "t.db")
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        conn.close()

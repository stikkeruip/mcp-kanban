"""Phase 3 tests: TaskService against an in-memory SQLite repository."""

from datetime import datetime, timedelta, timezone

import pytest

from tasks_mcp.domain.task import Priority, Status
from tasks_mcp.domain.transitions import FreeTransitionPolicy
from tasks_mcp.services.errors import InvalidTransition, TaskNotFound, ValidationError
from tasks_mcp.services.task_service import TaskService
from tasks_mcp.storage.migrations.runner import run_migrations
from tasks_mcp.storage.sqlite_repository import SqliteTaskRepository, connect


class FakeClock:
    """Injectable clock: every call advances one second, so timestamp
    ordering is deterministic in tests."""

    def __init__(self):
        self.current = datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        self.current += timedelta(seconds=1)
        return self.current


class RefuseAllPolicy:
    """Stub policy proving the transition seam: refuses every move."""

    def can_move(self, current, target) -> bool:
        return False


@pytest.fixture
def repo():
    conn = connect(":memory:")
    run_migrations(conn)
    yield SqliteTaskRepository(conn)
    conn.close()


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def service(repo, clock):
    return TaskService(repo, FreeTransitionPolicy(), now=clock)


class TestAddTask:
    def test_defaults_land_in_backlog(self, service):
        task = service.add_task("Buy milk")
        assert task.id is not None
        assert task.status is Status.BACKLOG
        assert task.priority is Priority.NORMAL
        assert task.tags == []
        assert task.description is None
        assert task.archived is False
        assert task.created_at == task.updated_at

    def test_all_fields(self, service):
        task = service.add_task(
            "Ship it", description="v1 release", priority="high", tags=["work", "mcp"]
        )
        assert task.description == "v1 release"
        assert task.priority is Priority.HIGH
        assert task.tags == ["work", "mcp"]

    def test_title_is_stripped(self, service):
        assert service.add_task("  padded  ").title == "padded"

    @pytest.mark.parametrize("bad", ["", "   ", None, 42])
    def test_bad_title_raises(self, service, bad):
        with pytest.raises(ValidationError):
            service.add_task(bad)

    def test_unknown_priority_raises(self, service):
        with pytest.raises(ValidationError, match="priority"):
            service.add_task("x", priority="urgent")

    def test_tags_are_stripped_and_deduped(self, service):
        task = service.add_task("x", tags=[" a ", "b", "a"])
        assert task.tags == ["a", "b"]

    @pytest.mark.parametrize("bad", [["ok", ""], ["ok", None], "not-a-list"])
    def test_bad_tags_raise(self, service, bad):
        with pytest.raises(ValidationError):
            service.add_task("x", tags=bad)

    def test_empty_description_normalizes_to_none(self, service):
        assert service.add_task("x", description="   ").description is None

    def test_link_is_stored_and_blank_normalizes_to_none(self, service):
        task = service.add_task("x", link="cd C:\\p; claude -r abc")
        assert task.link == "cd C:\\p; claude -r abc"
        assert service.add_task("y", link="   ").link is None


class TestGetAndList:
    def test_get_missing_raises(self, service):
        with pytest.raises(TaskNotFound, match="999"):
            service.get_task(999)

    def test_get_returns_archived_tasks_too(self, service):
        task = service.add_task("old")
        service.archive_task(task.id)
        assert service.get_task(task.id).archived is True

    def test_list_filters_accept_strings(self, service):
        service.add_task("a", tags=["home"])
        b = service.add_task("b", priority="high", tags=["work"])
        service.move_task(b.id, "testing")
        assert [t.id for t in service.list_tasks(status="testing")] == [b.id]
        assert [t.id for t in service.list_tasks(priority="high")] == [b.id]
        assert [t.title for t in service.list_tasks(tag="home")] == ["a"]

    def test_list_unknown_status_raises(self, service):
        with pytest.raises(ValidationError, match="status"):
            service.list_tasks(status="doing")


class TestEditTask:
    def test_partial_edit_keeps_other_fields(self, service):
        task = service.add_task("Title", description="desc", tags=["t"])
        edited = service.edit_task(task.id, priority="low")
        assert edited.title == "Title"
        assert edited.description == "desc"
        assert edited.tags == ["t"]
        assert edited.priority is Priority.LOW

    def test_edit_bumps_updated_at_only(self, service):
        task = service.add_task("x")
        edited = service.edit_task(task.id, title="y")
        assert edited.updated_at > task.updated_at
        assert edited.created_at == task.created_at

    def test_empty_string_clears_description(self, service):
        task = service.add_task("x", description="to be removed")
        assert service.edit_task(task.id, description="").description is None

    def test_edit_nothing_raises(self, service):
        task = service.add_task("x")
        with pytest.raises(ValidationError, match="nothing to update"):
            service.edit_task(task.id)

    def test_edit_missing_task_raises(self, service):
        with pytest.raises(TaskNotFound):
            service.edit_task(999, title="y")

    def test_edit_cannot_blank_title(self, service):
        task = service.add_task("x")
        with pytest.raises(ValidationError):
            service.edit_task(task.id, title="  ")

    def test_link_alone_is_a_valid_edit_and_empty_string_clears(self, service):
        task = service.add_task("x")
        edited = service.edit_task(task.id, link="cd C:\\p; claude -r abc")
        assert edited.link == "cd C:\\p; claude -r abc"
        assert service.edit_task(task.id, link="").link is None


class TestMoveTask:
    def test_full_cycle_and_back(self, service):
        task = service.add_task("traveler")
        for target in ["in_progress", "testing", "done", "backlog"]:
            task = service.move_task(task.id, target)
            assert task.status == Status(target)

    def test_move_accepts_enum(self, service):
        task = service.add_task("x")
        assert service.move_task(task.id, Status.DONE).status is Status.DONE

    def test_move_bumps_updated_at(self, service):
        task = service.add_task("x")
        moved = service.move_task(task.id, "testing")
        assert moved.updated_at > task.updated_at

    def test_unknown_status_raises(self, service):
        task = service.add_task("x")
        with pytest.raises(ValidationError, match="status"):
            service.move_task(task.id, "shipped")

    def test_missing_task_raises(self, service):
        with pytest.raises(TaskNotFound):
            service.move_task(999, "done")

    def test_refusing_policy_raises_invalid_transition(self, repo, clock):
        """The seam: a strict policy plugs in with zero service changes."""
        strict = TaskService(repo, RefuseAllPolicy(), now=clock)
        task = strict.add_task("stuck")
        with pytest.raises(InvalidTransition, match="backlog.*testing"):
            strict.move_task(task.id, "testing")
        assert strict.get_task(task.id).status is Status.BACKLOG


class TestArchiveTask:
    def test_archive_hides_from_default_listing_but_keeps_row(self, service):
        task = service.add_task("x")
        service.archive_task(task.id)
        assert service.list_tasks() == []
        assert service.list_tasks(include_archived=True)[0].id == task.id
        assert service.get_task(task.id).archived is True

    def test_archive_is_idempotent(self, service):
        task = service.add_task("x")
        first = service.archive_task(task.id)
        second = service.archive_task(task.id)
        assert second.updated_at == first.updated_at

    def test_archive_missing_raises(self, service):
        with pytest.raises(TaskNotFound):
            service.archive_task(999)


class TestGetBoard:
    def test_empty_board_has_all_four_columns_in_order(self, service):
        board = service.get_board()
        assert [c["status"] for c in board["columns"]] == [
            Status.BACKLOG,
            Status.IN_PROGRESS,
            Status.TESTING,
            Status.DONE,
        ]
        assert all(c["tasks"] == [] for c in board["columns"])

    def test_tasks_land_in_their_columns(self, service):
        a = service.add_task("a")
        b = service.add_task("b")
        service.move_task(b.id, "testing")
        board = service.get_board()
        by_status = {c["status"]: c["tasks"] for c in board["columns"]}
        assert [t.id for t in by_status[Status.BACKLOG]] == [a.id]
        assert [t.id for t in by_status[Status.TESTING]] == [b.id]

    def test_archived_tasks_do_not_appear(self, service):
        task = service.add_task("gone")
        service.archive_task(task.id)
        board = service.get_board()
        assert all(c["tasks"] == [] for c in board["columns"])

    def test_board_reflects_full_travel(self, service):
        """Definition-of-done check: backlog → in_progress → testing → done
        and freely back, visible on the board at each stop."""
        task = service.add_task("traveler")
        for target in [Status.IN_PROGRESS, Status.TESTING, Status.DONE, Status.BACKLOG]:
            service.move_task(task.id, target)
            by_status = {
                c["status"]: c["tasks"] for c in service.get_board()["columns"]
            }
            assert [t.id for t in by_status[target]] == [task.id]

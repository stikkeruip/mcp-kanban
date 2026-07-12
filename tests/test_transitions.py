"""Phase 1 tests: domain enums and the free transition policy."""

from itertools import product

from tasks_mcp.domain.task import Priority, Status
from tasks_mcp.domain.transitions import FreeTransitionPolicy


class TestStatus:
    def test_values(self):
        assert [s.value for s in Status] == [
            "backlog",
            "in_progress",
            "testing",
            "done",
        ]

    def test_board_order_is_declaration_order(self):
        assert list(Status) == [
            Status.BACKLOG,
            Status.IN_PROGRESS,
            Status.TESTING,
            Status.DONE,
        ]

    def test_compares_to_plain_strings(self):
        assert Status.BACKLOG == "backlog"
        assert Status("in_progress") is Status.IN_PROGRESS


class TestPriority:
    def test_values(self):
        assert [p.value for p in Priority] == ["low", "normal", "high"]

    def test_compares_to_plain_strings(self):
        assert Priority.HIGH == "high"
        assert Priority("low") is Priority.LOW


class TestFreeTransitionPolicy:
    def test_allows_every_pair_including_self_moves(self):
        policy = FreeTransitionPolicy()
        for current, target in product(Status, Status):
            assert policy.can_move(current, target) is True

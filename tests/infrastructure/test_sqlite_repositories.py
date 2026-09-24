from datetime import date, datetime, timezone

import pytest

from companion.domain.errors import NotFoundError, ValidationError
from companion.domain.models import Goal, Memory, MemoryKind, MemoryQuery, Priority, Task
from companion.infrastructure.sqlite.database import SQLiteDatabase
from companion.infrastructure.sqlite.repositories import (
    SQLiteGoalRepository,
    SQLiteMemoryRepository,
    SQLiteTaskRepository,
)


@pytest.fixture
def repositories(tmp_path):
    database = SQLiteDatabase(tmp_path / "companion.sqlite3")
    database.initialize()
    return (
        SQLiteGoalRepository(database),
        SQLiteTaskRepository(database),
        SQLiteMemoryRepository(database),
    )


def make_goal(goal_id="goal-1", active=True, priority=Priority.P1):
    return Goal(id=goal_id, name=f"Goal {goal_id}", priority=priority, active=active)


def make_task(
    goal_id="goal-1",
    task_id="task-1",
    priority=Priority.P1,
    hard_end=None,
    created_at=None,
    target_units=None,
):
    return Task(
        id=task_id,
        title=f"Task {task_id}",
        goal_id=goal_id,
        due_date=date(2026, 9, 24),
        planned_minutes=30,
        priority=priority,
        hard_end=hard_end,
        created_at=created_at or datetime(2026, 9, 24, tzinfo=timezone.utc),
        target_units=target_units,
    )


def make_memory(
    memory_id,
    content,
    *,
    kind=MemoryKind.PREFERENCE,
    source="user",
    importance=3,
    created_at=None,
    expires_at=None,
):
    return Memory(
        id=memory_id,
        kind=kind,
        content=content,
        source=source,
        importance=importance,
        created_at=created_at or datetime(2026, 9, 24, tzinfo=timezone.utc),
        expires_at=expires_at,
    )


def test_goal_task_and_memory_round_trip_after_reopening_database(tmp_path):
    database = SQLiteDatabase(tmp_path / "companion.sqlite3")
    database.initialize()
    goals = SQLiteGoalRepository(database)
    tasks = SQLiteTaskRepository(database)
    memories = SQLiteMemoryRepository(database)
    goal = make_goal()
    task = make_task(target_units=4)
    memory = make_memory("memory-1", "Prefers short sessions", importance=4)
    goals.add(goal)
    tasks.add(task)
    memories.add(memory)

    assert SQLiteGoalRepository(database).get(goal.id) == goal
    assert SQLiteTaskRepository(database).get(task.id) == task
    assert SQLiteMemoryRepository(database).search(MemoryQuery()) == [memory]


def test_goal_repository_lists_only_active_goals(repositories):
    goals, _, _ = repositories
    goals.add(make_goal("active", active=True))
    goals.add(make_goal("inactive", active=False))
    assert [goal.id for goal in goals.list_active()] == ["active"]


def test_goal_repository_converts_duplicate_id_to_validation_error(repositories):
    goals, _, _ = repositories
    goals.add(make_goal())
    with pytest.raises(ValidationError):
        goals.add(make_goal())


def test_goal_delete_is_restricted_while_task_exists(repositories):
    goals, tasks, _ = repositories
    goals.add(make_goal())
    tasks.add(make_task())
    with pytest.raises(ValidationError):
        goals.delete("goal-1")
    assert goals.get("goal-1") is not None


def test_goal_delete_of_missing_id_raises_not_found(repositories):
    goals, _, _ = repositories
    with pytest.raises(NotFoundError):
        goals.delete("missing")


def test_task_repository_rejects_missing_goal(repositories):
    _, tasks, _ = repositories
    with pytest.raises(ValidationError):
        tasks.add(make_task(goal_id="missing-goal"))


def test_task_repository_converts_duplicate_id_to_validation_error(repositories):
    goals, tasks, _ = repositories
    goals.add(make_goal())
    tasks.add(make_task())
    with pytest.raises(ValidationError):
        tasks.add(make_task())


def test_task_repository_sorts_priority_deadline_creation_and_id(repositories):
    goals, tasks, _ = repositories
    goals.add(make_goal())
    day = date(2026, 9, 24)
    early = datetime(2026, 9, 24, 9, tzinfo=timezone.utc)
    late = datetime(2026, 9, 24, 10, tzinfo=timezone.utc)
    tasks.add(make_task("goal-1", "p2", Priority.P2, created_at=early))
    tasks.add(make_task("goal-1", "p1-none", Priority.P1, created_at=early))
    tasks.add(make_task("goal-1", "p1-late", Priority.P1, hard_end=late, created_at=early))
    tasks.add(make_task("goal-1", "p1-early-b", Priority.P1, hard_end=early, created_at=late))
    tasks.add(make_task("goal-1", "p1-early-a", Priority.P1, hard_end=early, created_at=early))
    assert [task.id for task in tasks.list_for_day(day)] == [
        "p1-early-a", "p1-early-b", "p1-late", "p1-none", "p2",
    ]


def test_task_sort_uses_id_as_final_stable_tie_breaker(repositories):
    goals, tasks, _ = repositories
    goals.add(make_goal())
    deadline = datetime(2026, 9, 24, 9, tzinfo=timezone.utc)
    created = datetime(2026, 9, 24, 8, tzinfo=timezone.utc)
    tasks.add(make_task("goal-1", "same-b", hard_end=deadline, created_at=created))
    tasks.add(make_task("goal-1", "same-a", hard_end=deadline, created_at=created))
    assert [task.id for task in tasks.list_for_day(date(2026, 9, 24))] == ["same-a", "same-b"]


def test_task_repository_requires_calendar_date_for_day_listing(repositories):
    _, tasks, _ = repositories
    with pytest.raises(ValidationError):
        tasks.list_for_day(datetime(2026, 9, 24, tzinfo=timezone.utc))


def test_task_progress_update_changes_only_requested_task(repositories):
    goals, tasks, _ = repositories
    goals.add(make_goal())
    tasks.add(make_task(task_id="one", target_units=5))
    tasks.add(make_task(task_id="two", target_units=8))
    updated = tasks.set_completed_units("one", 2)
    assert updated.completed_units == 2
    assert tasks.get("two").completed_units == 0


def test_task_progress_rejects_invalid_value_and_unknown_task(repositories):
    goals, tasks, _ = repositories
    goals.add(make_goal())
    tasks.add(make_task(target_units=2))
    with pytest.raises(ValidationError):
        tasks.set_completed_units("task-1", 3)
    with pytest.raises(NotFoundError):
        tasks.set_completed_units("missing", 1)


def test_mark_completed_fills_unit_target(repositories):
    goals, tasks, _ = repositories
    goals.add(make_goal())
    tasks.add(make_task(target_units=4))
    task = tasks.mark_completed("task-1")
    assert task.completed_units == 4
    assert task.status.value == "completed"


def test_memory_search_filters_text_kind_and_source_and_hides_expired(repositories):
    _, _, memories = repositories
    memories.add(make_memory("pref", "Likes math", source="user", importance=5))
    memories.add(make_memory("journal", "Likes art", source="journal", importance=4))
    memories.add(make_memory("profile", "Likes math", kind=MemoryKind.PROFILE, importance=3))
    memories.add(
        make_memory(
            "expired", "Likes science", importance=5,
            expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
        )
    )
    result = memories.search(MemoryQuery(text="likes", kind=MemoryKind.PREFERENCE, source="user"))
    assert [memory.id for memory in result] == ["pref"]


def test_memory_search_sorts_importance_then_recency_and_obeys_limit(repositories):
    _, _, memories = repositories
    old = datetime(2026, 9, 20, tzinfo=timezone.utc)
    newer = datetime(2026, 9, 21, tzinfo=timezone.utc)
    memories.add(make_memory("low", "one", importance=2, created_at=newer))
    memories.add(make_memory("older", "two", importance=4, created_at=old))
    memories.add(make_memory("newer", "three", importance=4, created_at=newer))
    assert [memory.id for memory in memories.search(MemoryQuery(), limit=2)] == ["newer", "older"]


def test_memory_search_can_include_expired_and_requires_positive_limit(repositories):
    _, _, memories = repositories
    memories.add(
        make_memory("expired", "old", expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc))
    )
    assert [memory.id for memory in memories.search(MemoryQuery(include_expired=True))] == ["expired"]
    with pytest.raises(ValidationError):
        memories.search(MemoryQuery(), limit=0)


def test_memory_repository_converts_duplicate_id_to_validation_error(repositories):
    _, _, memories = repositories
    memories.add(make_memory("duplicate", "first"))
    with pytest.raises(ValidationError):
        memories.add(make_memory("duplicate", "second"))


def test_memory_delete_only_removes_requested_id(repositories):
    _, _, memories = repositories
    memories.add(make_memory("one", "one"))
    memories.add(make_memory("two", "two"))
    memories.delete("one")
    assert [memory.id for memory in memories.search(MemoryQuery())] == ["two"]
    with pytest.raises(NotFoundError):
        memories.delete("one")

from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone

import pytest

from companion.domain.errors import ValidationError
from companion.domain.models import (
    Goal,
    Memory,
    MemoryKind,
    MemoryQuery,
    Priority,
    Task,
    TaskStatus,
)


def make_goal(**changes):
    values = {"id": "goal-1", "name": "Study", "priority": Priority.P1}
    values.update(changes)
    return Goal(**values)


def make_task(**changes):
    values = {
        "id": "task-1",
        "title": "Read",
        "goal_id": "goal-1",
        "due_date": date(2026, 9, 24),
        "planned_minutes": 30,
        "priority": Priority.P1,
        "created_at": datetime(2026, 9, 24, tzinfo=timezone.utc),
    }
    values.update(changes)
    return Task(**values)


def make_memory(**changes):
    values = {
        "id": "memory-1",
        "kind": MemoryKind.PREFERENCE,
        "content": "Prefers short sessions",
        "source": "user",
        "importance": 3,
        "created_at": datetime(2026, 9, 24, tzinfo=timezone.utc),
    }
    values.update(changes)
    return Memory(**values)


def test_priority_values_and_task_status_are_stable():
    assert [Priority.P0, Priority.P1, Priority.P2] == [0, 1, 2]
    assert [TaskStatus.OPEN.value, TaskStatus.COMPLETED.value] == ["open", "completed"]


def test_task_is_immutable():
    task = make_task()
    with pytest.raises(FrozenInstanceError):
        task.title = "Changed"


@pytest.mark.parametrize("factory, field", [(make_goal, "name"), (make_task, "title")])
@pytest.mark.parametrize("value", ["", "   "])
def test_goal_and_task_names_must_not_be_blank(factory, field, value):
    with pytest.raises(ValidationError):
        factory(**{field: value})


def test_task_rejects_unsupported_priority():
    with pytest.raises(ValidationError):
        make_task(priority=3)


@pytest.mark.parametrize("changes", [{"planned_minutes": -1}, {"completed_units": -1}])
def test_task_rejects_negative_minutes_or_progress(changes):
    with pytest.raises(ValidationError):
        make_task(**changes)


@pytest.mark.parametrize("target_units", [0, -1])
def test_task_requires_a_positive_unit_target(target_units):
    with pytest.raises(ValidationError):
        make_task(target_units=target_units)


def test_task_progress_cannot_exceed_target():
    with pytest.raises(ValidationError):
        make_task(target_units=2, completed_units=3)


def test_hard_end_cannot_be_before_hard_start():
    start = datetime(2026, 9, 24, 12, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        make_task(hard_start=start, hard_end=start - timedelta(minutes=1))


@pytest.mark.parametrize(
    "changes",
    [
        {"created_at": datetime(2026, 9, 24)},
        {"hard_start": datetime(2026, 9, 24)},
    ],
)
def test_task_rejects_naive_datetimes(changes):
    with pytest.raises(ValidationError):
        make_task(**changes)


def test_task_normalizes_aware_datetimes_to_utc():
    local_time = datetime(2026, 9, 24, 8, tzinfo=timezone(timedelta(hours=8)))
    assert make_task(created_at=local_time).created_at == datetime(2026, 9, 24, tzinfo=timezone.utc)


def test_goal_and_memory_validate_priority_and_content():
    with pytest.raises(ValidationError):
        make_goal(priority=4)
    with pytest.raises(ValidationError):
        make_memory(content="  ")
    with pytest.raises(ValidationError):
        make_memory(importance=6)


def test_memory_query_is_immutable_and_defaults_to_live_memories():
    query = MemoryQuery()
    assert query.include_expired is False
    with pytest.raises(FrozenInstanceError):
        query.text = "secret"

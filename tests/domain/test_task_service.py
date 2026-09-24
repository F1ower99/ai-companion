from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from threading import Barrier

import pytest

from companion.domain.errors import NotFoundError, ValidationError
from companion.domain.models import Goal, Priority, Task, TaskStatus
from companion.application.task_service import TaskService
from companion.infrastructure.sqlite.database import SQLiteDatabase
from companion.infrastructure.sqlite.repositories import (
    SQLiteGoalRepository,
    SQLiteTaskRepository,
)


class FakeGoalRepository:
    def __init__(self, goals):
        self.items = {goal.id: goal for goal in goals}

    def add(self, goal):
        if goal.id in self.items:
            raise ValidationError("Goal already exists.")
        self.items[goal.id] = goal

    def get(self, goal_id):
        return self.items.get(goal_id)

    def list_active(self):
        return [goal for goal in self.items.values() if goal.active]


class FakeTaskRepository:
    def __init__(self, tasks):
        self.items = {task.id: task for task in tasks}

    def add(self, task):
        if task.id in self.items:
            raise ValidationError("Task already exists.")
        self.items[task.id] = task

    def get(self, task_id):
        return self.items.get(task_id)

    def list_for_day(self, day):
        return [task for task in self.items.values() if task.due_date == day]

    def set_completed_units(self, task_id, value):
        updated = replace(self.items[task_id], completed_units=value)
        self.items[task_id] = updated
        return updated

    def increment_completed_units(self, task_id, count):
        task = self.items.get(task_id)
        if task is None:
            raise NotFoundError("Task not found.")
        if task.target_units is None:
            raise ValidationError("This task has no unit target.")
        return self.set_completed_units(
            task_id, min(task.completed_units + count, task.target_units)
        )

    def mark_completed(self, task_id):
        task = self.items[task_id]
        completed_units = task.target_units if task.target_units is not None else task.completed_units
        updated = replace(
            task, completed_units=completed_units,
            status=TaskStatus.COMPLETED,
        )
        self.items[task_id] = updated
        return updated


def make_goal(active=True):
    return Goal(id="goal-1", name="Study", priority=Priority.P1, active=active)


def make_task(task_id):
    return Task(
        id=task_id,
        title="Read",
        goal_id="goal-1",
        due_date=date(2026, 9, 24),
        planned_minutes=30,
        priority=Priority.P1,
        created_at=datetime(2026, 9, 24, tzinfo=timezone.utc),
    )


@pytest.fixture
def service():
    goals = FakeGoalRepository([make_goal()])
    tasks = FakeTaskRepository([
        replace(make_task("task-1"), target_units=10),
        make_task("task-2"),
    ])
    return TaskService(goals, tasks)


def test_add_goal_generates_id_and_lists_active_goals(service):
    goal = service.add_goal("Exercise", target="3 days", priority=Priority.P0)
    assert goal.name == "Exercise"
    assert len(goal.id) == 36
    assert [item.id for item in service.list_active_goals()] == ["goal-1", goal.id]


def test_add_task_uses_utc_creation_time(service):
    task = service.add_task(
        title="  Review  ",
        goal_id="goal-1",
        due_date=date(2026, 9, 24),
        planned_minutes=45,
        priority=Priority.P0,
    )
    assert task.title == "Review"
    assert task.created_at.tzinfo == timezone.utc
    assert service.tasks.get(task.id) == task


@pytest.mark.parametrize(
    "values",
    [
        {"title": "  "},
        {"goal_id": "missing"},
        {"planned_minutes": -1},
        {"target_units": 0},
    ],
)
def test_add_task_rejects_invalid_fields_or_unknown_goal(service, values):
    args = {
        "title": "Read",
        "goal_id": "goal-1",
        "due_date": date(2026, 9, 24),
        "planned_minutes": 30,
        "priority": Priority.P1,
    }
    args.update(values)
    with pytest.raises(ValidationError):
        service.add_task(**args)


def test_add_task_rejects_inactive_goal(service):
    service.goals.add(Goal(id="inactive", name="Inactive", active=False))
    with pytest.raises(ValidationError):
        service.add_task(
            title="Read", goal_id="inactive", due_date=date(2026, 9, 24),
            planned_minutes=30, priority=Priority.P1,
        )


def test_add_task_rejects_reversed_hard_times(service):
    start = datetime(2026, 9, 24, 12, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        service.add_task(
            title="Read", goal_id="goal-1", due_date=date(2026, 9, 24),
            planned_minutes=30, priority=Priority.P1,
            hard_start=start, hard_end=datetime(2026, 9, 24, 11, tzinfo=timezone.utc),
        )


def test_complete_units_requires_positive_count_and_target(service):
    for count in (0, -1):
        with pytest.raises(ValidationError):
            service.complete_units("task-1", count)
    with pytest.raises(ValidationError):
        service.complete_units("task-2", 1)


def test_complete_units_clamps_to_target_and_isolates_other_tasks(service):
    task = service.complete_units("task-1", 20)
    assert task.completed_units == 10
    assert service.tasks.get("task-2").completed_units == 0


def test_complete_units_unknown_task_raises_not_found(service):
    with pytest.raises(NotFoundError):
        service.complete_units("missing", 1)


def test_concurrent_unit_increments_do_not_lose_progress(tmp_path):
    database = SQLiteDatabase(tmp_path / "companion.sqlite3")
    database.initialize()
    goals = SQLiteGoalRepository(database)
    stored_tasks = SQLiteTaskRepository(database)
    goals.add(make_goal())
    task = replace(make_task("task-1"), target_units=10)
    stored_tasks.add(task)

    read_barrier = Barrier(2)

    class SynchronizedTaskRepository:
        def __init__(self, repository):
            self.repository = repository

        def get(self, task_id):
            task = self.repository.get(task_id)
            read_barrier.wait(timeout=5)
            return task

        def __getattr__(self, name):
            return getattr(self.repository, name)

    service = TaskService(goals, SynchronizedTaskRepository(stored_tasks))
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [
            workers.submit(service.complete_units, task.id, 1)
            for _ in range(2)
        ]
        for future in futures:
            future.result(timeout=8)

    assert stored_tasks.get(task.id).completed_units == 2


def test_mark_completed_fills_quantity_target_and_completes_normal_task(service):
    count_task = service.mark_completed("task-1")
    ordinary_task = service.mark_completed("task-2")
    assert count_task.completed_units == 10
    assert count_task.status is TaskStatus.COMPLETED
    assert ordinary_task.status is TaskStatus.COMPLETED

from datetime import date, datetime
from uuid import uuid4

from companion.domain.errors import ValidationError
from companion.domain.models import Goal, Priority, Task
from companion.ports.clock import Clock
from companion.ports.repositories import GoalRepository, TaskRepository


class TaskService:
    def __init__(self, goals: GoalRepository, tasks: TaskRepository, clock: Clock) -> None:
        self.goals = goals
        self.tasks = tasks
        self.clock = clock

    def add_goal(
        self,
        name: str,
        target: str | None = None,
        priority: Priority = Priority.P1,
    ) -> Goal:
        goal = Goal(
            id=str(uuid4()),
            name=name,
            target=target,
            priority=priority,
            created_at=self.clock.now_utc(),
        )
        self.goals.add(goal)
        return goal

    def list_active_goals(self) -> list[Goal]:
        return self.goals.list_active()

    def add_task(
        self,
        title: str,
        goal_id: str,
        due_date: date,
        planned_minutes: int,
        priority: Priority,
        planned_start_at: datetime | None = None,
        target_units: int | None = None,
        hard_start: datetime | None = None,
        hard_end: datetime | None = None,
    ) -> Task:
        goal = self.goals.get(goal_id)
        if goal is None:
            raise ValidationError("The selected goal does not exist.")
        if not goal.active:
            raise ValidationError("The selected goal is inactive.")
        task = Task(
            id=str(uuid4()),
            title=title,
            goal_id=goal_id,
            due_date=due_date,
            planned_minutes=planned_minutes,
            priority=priority,
            planned_start_at=planned_start_at,
            target_units=target_units,
            hard_start=hard_start,
            hard_end=hard_end,
            created_at=self.clock.now_utc(),
        )
        self.tasks.add(task)
        return task

    def list_for_day(self, day: date) -> list[Task]:
        return self.tasks.list_for_day(day)

    def list_for_decisions(
        self, day: date, day_start_utc: datetime, next_day_start_utc: datetime
    ) -> list[Task]:
        return self.tasks.list_for_decisions(day, day_start_utc, next_day_start_utc)

    def get_task(self, task_id: str) -> Task | None:
        return self.tasks.get(task_id)

    def complete_units(self, task_id: str, count: int) -> Task:
        if type(count) is not int or count <= 0:
            raise ValidationError("Progress increment must be a positive integer.")
        return self.tasks.increment_completed_units(task_id, count)

    def mark_completed(self, task_id: str) -> Task:
        return self.tasks.mark_completed(task_id)

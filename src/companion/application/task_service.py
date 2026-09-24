from datetime import date, datetime
from uuid import uuid4

from companion.domain.errors import NotFoundError, ValidationError
from companion.domain.models import Goal, Priority, Task, utc_now
from companion.ports.repositories import GoalRepository, TaskRepository


class TaskService:
    def __init__(self, goals: GoalRepository, tasks: TaskRepository) -> None:
        self.goals = goals
        self.tasks = tasks

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
            created_at=utc_now(),
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
            target_units=target_units,
            hard_start=hard_start,
            hard_end=hard_end,
            created_at=utc_now(),
        )
        self.tasks.add(task)
        return task

    def list_for_day(self, day: date) -> list[Task]:
        return self.tasks.list_for_day(day)

    def complete_units(self, task_id: str, count: int) -> Task:
        if type(count) is not int or count <= 0:
            raise ValidationError("Progress increment must be a positive integer.")
        task = self.tasks.get(task_id)
        if task is None:
            raise NotFoundError("Task not found.")
        if task.target_units is None:
            raise ValidationError("This task has no unit target.")
        value = min(task.completed_units + count, task.target_units)
        return self.tasks.set_completed_units(task_id, value)

    def mark_completed(self, task_id: str) -> Task:
        return self.tasks.mark_completed(task_id)

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Sequence

from companion.domain.calendar import CourseOccurrence
from companion.domain.errors import ValidationError
from companion.domain.models import Task, TaskStatus
from companion.domain.reminders import remaining_minutes


def _require_day(day: date) -> None:
    if not isinstance(day, date) or isinstance(day, datetime):
        raise ValidationError("Study plan day must be a calendar date.")


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{field_name} must include a timezone.")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class HardDeadlineSummary:
    task_id: str
    title: str
    hard_end: datetime
    remaining_minutes: int
    overdue: bool

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str) or not self.task_id.strip():
            raise ValidationError("task_id must not be blank.")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValidationError("Deadline title must not be blank.")
        object.__setattr__(self, "title", self.title.strip())
        object.__setattr__(self, "hard_end", _aware_utc(self.hard_end, "hard_end"))
        if type(self.remaining_minutes) is not int or self.remaining_minutes < 0:
            raise ValidationError("remaining_minutes must be a non-negative integer.")
        if not isinstance(self.overdue, bool):
            raise ValidationError("overdue must be a boolean.")


@dataclass(frozen=True)
class StudyPlanSummary:
    day: date
    courses: tuple[CourseOccurrence, ...]
    remaining_tasks: tuple[Task, ...]
    total_remaining_minutes: int
    hard_deadlines: tuple[HardDeadlineSummary, ...]

    def __post_init__(self) -> None:
        _require_day(self.day)
        if not isinstance(self.courses, tuple) or any(
            not isinstance(course, CourseOccurrence) for course in self.courses
        ):
            raise ValidationError("courses must be a tuple of CourseOccurrence values.")
        if not isinstance(self.remaining_tasks, tuple) or any(
            not isinstance(task, Task) for task in self.remaining_tasks
        ):
            raise ValidationError("remaining_tasks must be a tuple of Task values.")
        if type(self.total_remaining_minutes) is not int or self.total_remaining_minutes < 0:
            raise ValidationError("total_remaining_minutes must be a non-negative integer.")
        if not isinstance(self.hard_deadlines, tuple) or any(
            not isinstance(item, HardDeadlineSummary) for item in self.hard_deadlines
        ):
            raise ValidationError("hard_deadlines must be a tuple of HardDeadlineSummary values.")


def build_study_plan(
    day: date,
    tasks: Sequence[Task],
    courses: Sequence[CourseOccurrence],
    as_of_utc: datetime,
) -> StudyPlanSummary:
    """Build an immutable, read-only summary over caller-selected snapshots."""
    _require_day(day)
    as_of = _aware_utc(as_of_utc, "as_of_utc")
    if not isinstance(tasks, Sequence) or isinstance(tasks, (str, bytes)):
        raise ValidationError("tasks must be a sequence of Task values.")
    if not isinstance(courses, Sequence) or isinstance(courses, (str, bytes)):
        raise ValidationError("courses must be a sequence of CourseOccurrence values.")

    for task in tasks:
        if not isinstance(task, Task):
            raise ValidationError("tasks must contain Task values.")
    for course in courses:
        if not isinstance(course, CourseOccurrence):
            raise ValidationError("courses must contain CourseOccurrence values.")
        if course.day != day:
            raise ValidationError("All supplied courses must match the requested day.")

    open_tasks = [task for task in tasks if task.status is TaskStatus.OPEN]
    max_time = datetime.max.replace(tzinfo=timezone.utc)
    sorted_tasks = tuple(sorted(
        open_tasks,
        key=lambda task: (
            int(task.priority),
            task.hard_end is None,
            task.hard_end or max_time,
            task.planned_start_at is None,
            task.planned_start_at or max_time,
            task.title.casefold(),
            task.id,
        ),
    ))
    deadline_summaries = tuple(sorted(
        (
            HardDeadlineSummary(
                task_id=task.id,
                title=task.title,
                hard_end=task.hard_end,
                remaining_minutes=remaining_minutes(task),
                overdue=task.hard_end <= as_of,
            )
            for task in open_tasks
            if task.hard_end is not None
        ),
        key=lambda item: (item.hard_end, item.task_id),
    ))
    return StudyPlanSummary(
        day=day,
        courses=tuple(courses),
        remaining_tasks=sorted_tasks,
        total_remaining_minutes=sum(remaining_minutes(task) for task in sorted_tasks),
        hard_deadlines=deadline_summaries,
    )

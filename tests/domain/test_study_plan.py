from dataclasses import FrozenInstanceError
from datetime import date, datetime, time, timedelta, timezone

import pytest

from companion.domain.calendar import CourseOccurrence
from companion.domain.errors import ValidationError
from companion.domain.models import Priority, Task, TaskStatus
from companion.domain.study_plan import StudyPlanSummary, build_study_plan


UTC = timezone.utc
DAY = date(2026, 9, 26)
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def make_task(task_id, **changes):
    values = {
        "id": task_id,
        "title": task_id.title(),
        "goal_id": "study",
        "due_date": DAY,
        "planned_minutes": 30,
        "priority": Priority.P1,
        "created_at": NOW - timedelta(days=1),
    }
    values.update(changes)
    return Task(**values)


def make_course(rule_id="lecture"):
    return CourseOccurrence(
        term_id="fall",
        rule_id=rule_id,
        day=DAY,
        week_number=3,
        weekday=5,
        start_time=time(9, 0),
        end_time=time(10, 0),
        course_name="History",
    )


def test_summary_filters_completed_tasks_and_keeps_supplied_courses():
    open_task = make_task("open")
    completed_task = make_task("done", status=TaskStatus.COMPLETED)
    course = make_course()
    result = build_study_plan(DAY, [completed_task, open_task], [course], NOW)
    assert isinstance(result, StudyPlanSummary)
    assert result.day == DAY
    assert result.remaining_tasks == (open_task,)
    assert result.total_remaining_minutes == 30
    assert result.courses == (course,)


def test_remaining_task_minutes_use_stage_three_progress_rounding():
    task = make_task("units", planned_minutes=90, target_units=3, completed_units=1)
    result = build_study_plan(DAY, [task], [], NOW)
    assert result.total_remaining_minutes == 60
    assert result.hard_deadlines == ()


def test_remaining_tasks_have_stable_priority_deadline_start_title_id_order():
    later_priority = make_task("p2", priority=Priority.P2)
    no_deadline = make_task("no-deadline", title="A", hard_end=None)
    later_deadline = make_task(
        "later", title="Later", hard_end=NOW + timedelta(hours=3),
    )
    earlier_deadline = make_task(
        "earlier", title="Earlier", hard_end=NOW + timedelta(hours=1),
    )
    p0_task = make_task("p0", priority=Priority.P0, hard_end=NOW + timedelta(hours=4))
    result = build_study_plan(
        DAY,
        [later_priority, no_deadline, later_deadline, p0_task, earlier_deadline],
        [],
        NOW,
    )
    assert [task.id for task in result.remaining_tasks] == [
        "p0", "earlier", "later", "no-deadline", "p2",
    ]


def test_deadline_summaries_are_sorted_and_mark_equal_as_of_time_overdue():
    future = make_task("future", hard_end=NOW + timedelta(minutes=1))
    due_now = make_task("due-now", hard_end=NOW)
    past = make_task("past", hard_end=NOW - timedelta(minutes=1))
    result = build_study_plan(DAY, [future, due_now, past], [], NOW)
    assert [(item.task_id, item.overdue) for item in result.hard_deadlines] == [
        ("past", True), ("due-now", True), ("future", False),
    ]
    assert [item.remaining_minutes for item in result.hard_deadlines] == [30, 30, 30]


def test_summary_is_immutable_and_does_not_mutate_input_tasks():
    tasks = [make_task("first"), make_task("second", planned_minutes=15)]
    original = tuple(tasks)
    result = build_study_plan(DAY, tasks, [], NOW)
    assert tuple(tasks) == original
    with pytest.raises(FrozenInstanceError):
        result.day = date(2026, 9, 27)


@pytest.mark.parametrize(
    "day, as_of_utc",
    [
        (datetime(2026, 9, 26, 0, 0), NOW),
        (DAY, datetime(2026, 9, 26, 12, 0)),
    ],
)
def test_summary_rejects_datetime_as_calendar_day_and_naive_as_of(day, as_of_utc):
    with pytest.raises(ValidationError):
        build_study_plan(day, [], [], as_of_utc)


def test_summary_requires_supplied_courses_to_match_requested_day():
    wrong_day_course = CourseOccurrence(
        term_id="fall", rule_id="other", day=DAY + timedelta(days=1),
        week_number=3, weekday=6, start_time=time(9), end_time=time(10),
        course_name="History",
    )
    with pytest.raises(ValidationError, match="requested day"):
        build_study_plan(DAY, [], [wrong_day_course], NOW)

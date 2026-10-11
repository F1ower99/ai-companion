from datetime import date, datetime, time, timedelta, timezone

from companion.application.chat_context import DailyChatContextBuilder
from companion.domain.calendar import AcademicTerm, CourseRule
from companion.domain.models import Priority, Task, TaskStatus


TODAY = date(2026, 10, 11)
NOW = datetime(2026, 10, 11, 12, 10, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self):
        self.resolved = []

    def resolve_local(self, day, wall_time):
        self.resolved.append((day, wall_time))
        return datetime.combine(day, wall_time).replace(tzinfo=timezone.utc)


class FakeTaskRepository:
    def __init__(self, tasks):
        self.tasks = tasks
        self.bounds = None

    def list_for_decisions(self, day, day_start_utc, next_day_start_utc):
        self.bounds = (day, day_start_utc, next_day_start_utc)
        return self.tasks


class FakeCalendarRepository:
    def __init__(self, term, rules):
        self.term = term
        self.rules = rules

    def list_terms(self):
        return [self.term]

    def list_rules(self, term_id):
        assert term_id == self.term.id
        return self.rules

    def list_exceptions(self, term_id):
        assert term_id == self.term.id
        return []


def make_task(task_id, title, priority=Priority.P1, *, end=None, completed=0, target=None, status=TaskStatus.OPEN):
    return Task(
        id=task_id,
        title=title,
        goal_id="goal",
        due_date=TODAY,
        planned_minutes=60,
        priority=priority,
        completed_units=completed,
        target_units=target,
        hard_end=end,
        status=status,
    )


def test_today_context_summarizes_open_tasks_with_progress_and_hard_deadlines():
    overdue = make_task(
        "p0", "核心任务", Priority.P0,
        end=NOW - timedelta(minutes=10), completed=2, target=4,
    )
    ordinary = make_task("p1", "普通任务", Priority.P1)
    completed = make_task("done", "已完成", status=TaskStatus.COMPLETED)
    tasks = FakeTaskRepository([ordinary, completed, overdue])
    term = AcademicTerm("fall", "秋季学期", date(2026, 9, 1), date(2026, 12, 31), date(2026, 8, 31))
    rules = [
        CourseRule(
            id=f"r{i:02}", term_id="fall", weekday=TODAY.weekday(),
            start_week=1, end_week=53, week_parity="all",
            start_time=time(9, i), end_time=time(10, i), course_name=f"课程{i:02}",
        )
        for i in range(10)
    ]
    clock = FakeClock()
    builder = DailyChatContextBuilder(tasks, FakeCalendarRepository(term, rules), clock)
    context = builder.build(TODAY, NOW)

    assert tasks.bounds == (
        TODAY,
        datetime(2026, 10, 11, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 12, 0, tzinfo=timezone.utc),
    )
    assert [task.id for task in context.tasks] == ["p0", "p1"]
    assert context.tasks[0].priority == "P0"
    assert context.tasks[0].remaining_minutes == 30
    assert context.tasks[0].deadline_status.startswith("已过期")
    assert context.tasks[1].remaining_minutes == 60
    assert len(context.courses) == 8
    assert context.omitted_course_count == 2
    assert "核心任务" in context.prompt_text()


def test_today_context_bounds_item_text_and_reports_omitted_records():
    tasks = FakeTaskRepository([
        make_task(f"t{i:02}", "长" * 250) for i in range(15)
    ])
    term = AcademicTerm("fall", "秋季", date(2026, 9, 1), date(2026, 12, 31), date(2026, 8, 31))
    rules = [
        CourseRule(
            id=f"r{i:02}", term_id="fall", weekday=TODAY.weekday(),
            start_week=1, end_week=53, week_parity="all",
            start_time=time(9), end_time=time(10), course_name="课程名" * 50,
        )
        for i in range(10)
    ]
    context = DailyChatContextBuilder(
        tasks, FakeCalendarRepository(term, rules), FakeClock()
    ).build(TODAY, NOW)

    assert len(context.tasks) == 12
    assert context.omitted_task_count == 3
    assert context.tasks[0].title.endswith("…")
    assert context.tasks[0].title_truncated
    assert len(context.courses) == 8
    assert context.courses[0].name.endswith("…")
    assert context.courses[0].name_truncated
    prompt = context.prompt_text()
    assert "省略 3 项" in prompt
    assert "省略 2 门" in prompt

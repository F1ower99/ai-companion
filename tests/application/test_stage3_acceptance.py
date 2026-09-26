from datetime import date, datetime, time, timedelta, timezone

from companion.application.proactive_reminder_service import ProactiveReminderService
from companion.application.task_service import TaskService
from companion.domain.decisions import DecisionKind, ReasonCode
from companion.domain.models import Goal, Priority, Task
from companion.domain.reminders import ActivitySnapshot, ActivityState, ReminderAction
from companion.infrastructure.sqlite.database import SQLiteDatabase
from companion.infrastructure.sqlite.repositories import (
    SQLiteGoalRepository,
    SQLiteReminderPreferencesRepository,
    SQLiteReminderRepository,
    SQLiteTaskRepository,
)
from companion.ports.clock import ClockSnapshot


UTC = timezone.utc
LOCAL = timezone(timedelta(hours=8))


class AcceptanceClock:
    def __init__(self, current):
        self.current = current

    def now_utc(self):
        return self.current

    def advance(self, minutes):
        self.current += timedelta(minutes=minutes)

    def resolve_local(self, day, wall):
        return datetime.combine(day, wall).replace(tzinfo=LOCAL).astimezone(UTC)

    def snapshot(self, preferences):
        local_now = self.current.astimezone(LOCAL)
        day = local_now.date()
        next_day = day + timedelta(days=1)
        wall = local_now.timetz().replace(tzinfo=None)
        return ClockSnapshot(
            now_utc=self.current,
            local_now=local_now,
            local_date=day,
            local_day_start_utc=self.resolve_local(day, time.min),
            next_local_day_start_utc=self.resolve_local(next_day, time.min),
            quiet_hours_active=wall >= preferences.quiet_start or wall < preferences.quiet_end,
            tonight_quiet_start_utc=self.resolve_local(day, preferences.quiet_start),
            quiet_period_end_utc=self.resolve_local(next_day, preferences.quiet_end),
        )


class FocusedThenIdleSource:
    def __init__(self):
        self.state = ActivityState.FOCUSED
        self.focus_started = datetime(2026, 9, 26, 10, tzinfo=UTC)

    def snapshot(self, at):
        since = self.focus_started if self.state is ActivityState.FOCUSED else at
        return ActivitySnapshot(self.state, at, since)


def make_task(task_id, title, priority, planned_at, planned_minutes, *, hard_end=None, target_units=None):
    return Task(
        id=task_id,
        title=title,
        goal_id="study",
        due_date=date(2026, 9, 26),
        planned_minutes=planned_minutes,
        priority=priority,
        target_units=target_units,
        planned_start_at=planned_at,
        hard_end=hard_end,
        created_at=datetime(2026, 9, 26, 8, tzinfo=UTC),
    )


def test_evening_focus_scenario_and_extension_re_evaluation_survive_restart(tmp_path):
    database = SQLiteDatabase(tmp_path / "companion.sqlite3")
    database.initialize()
    goals = SQLiteGoalRepository(database)
    tasks = SQLiteTaskRepository(database)
    goals.add(Goal("study", "Study"))
    vocabulary = make_task(
        "vocabulary", "Vocabulary", Priority.P1,
        datetime(2026, 9, 26, 11, 30, tzinfo=UTC),
        20,
        hard_end=datetime(2026, 9, 26, 13, 30, tzinfo=UTC),
        target_units=2,
    )
    course = make_task(
        "course", "Professional course", Priority.P0,
        datetime(2026, 9, 26, 13, 0, tzinfo=UTC),
        60,
    )
    tasks.add(vocabulary)
    tasks.add(course)
    clock = AcceptanceClock(datetime(2026, 9, 26, 11, 30, tzinfo=UTC))
    activity = FocusedThenIdleSource()

    def new_service():
        return ProactiveReminderService(
            clock,
            TaskService(goals, tasks, clock),
            SQLiteReminderRepository(database),
            SQLiteReminderPreferencesRepository(database),
            activity,
        )

    service = new_service()
    at_1930 = service.evaluate()
    assert at_1930.kind is DecisionKind.WAIT
    assert ReasonCode.BEFORE_PLANNED_START in at_1930.reason_codes

    clock.advance(40)
    at_2010 = service.evaluate()
    assert at_2010.kind is DecisionKind.SHOW_REMINDER
    assert at_2010.task_id == "vocabulary"
    assert ReasonCode.PLANNED_START_LATE in at_2010.reason_codes
    assert tasks.get("course").priority is Priority.P0

    # A fresh service sees the persisted display cooldown and cannot show a duplicate card.
    restarted = new_service()
    duplicate_tick = restarted.evaluate()
    assert duplicate_tick.kind is DecisionKind.WAIT
    assert ReasonCode.TASK_COOLDOWN in duplicate_tick.reason_codes

    extension = restarted.respond(
        "vocabulary", ReminderAction.EXTEND, minutes=30, idempotency_key="acceptance-extension"
    )
    assert extension.kind is DecisionKind.WAIT
    assert tasks.get("vocabulary").hard_end == vocabulary.hard_end
    tasks.set_completed_units("vocabulary", 1)
    activity.state = ActivityState.IDLE
    clock.advance(30)

    rechecked = new_service().evaluate()
    assert rechecked.kind is DecisionKind.WAIT
    assert ReasonCode.IDLE_USER in rechecked.reason_codes
    state = SQLiteReminderRepository(database).get_task_states(date(2026, 9, 26))
    assert next(item for item in state if item.task_id == "vocabulary").extension_count == 1
    with database.connection() as connection:
        kinds = [row[0] for row in connection.execute(
            "SELECT kind FROM reminder_events ORDER BY id"
        ).fetchall()]
    assert kinds.count("displayed") == 1
    assert kinds.count("extended") == 1

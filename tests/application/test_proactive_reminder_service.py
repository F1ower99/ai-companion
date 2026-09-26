from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone

import pytest

from companion.application.proactive_reminder_service import ProactiveReminderService
from companion.domain.decisions import DecisionKind, ReasonCode
from companion.domain.errors import StorageError, ValidationError
from companion.domain.models import Goal, Priority, Task, TaskStatus
from companion.domain.reminders import (
    ActivitySnapshot,
    ActivityState,
    ReminderAction,
    ReminderEvent,
    ReminderPreferences,
    TaskReminderState,
)
from companion.ports.clock import ClockSnapshot


UTC = timezone.utc
LOCAL = timezone(timedelta(hours=8))


class FixedClock:
    def __init__(self, current=None):
        self.current = current or datetime(2026, 9, 26, 12, 10, tzinfo=UTC)

    def now_utc(self):
        return self.current

    def advance(self, minutes):
        self.current += timedelta(minutes=minutes)

    def resolve_local(self, day, local_time):
        return datetime.combine(day, local_time).replace(tzinfo=LOCAL).astimezone(UTC)

    def snapshot(self, preferences):
        local_now = self.current.astimezone(LOCAL)
        day = local_now.date()
        next_day = day + timedelta(days=1)
        return ClockSnapshot(
            now_utc=self.current,
            local_now=local_now,
            local_date=day,
            local_day_start_utc=self.resolve_local(day, time.min),
            next_local_day_start_utc=self.resolve_local(next_day, time.min),
            quiet_hours_active=(local_now.time().replace(tzinfo=None) >= preferences.quiet_start
                                or local_now.time().replace(tzinfo=None) < preferences.quiet_end),
            tonight_quiet_start_utc=self.resolve_local(day, preferences.quiet_start),
            quiet_period_end_utc=self.resolve_local(next_day, preferences.quiet_end),
        )


class FakeTaskService:
    def __init__(self, tasks):
        self.items = {task.id: task for task in tasks}
        self.goals = [Goal("study", "Study")]
        self.list_calls = 0
        self.activity_mutation = None
        self.fail_completion = False

    def list_for_decisions(self, day, day_start_utc, next_day_start_utc):
        self.list_calls += 1
        return [
            task for task in self.items.values()
            if task.due_date <= day or (
                task.planned_start_at is not None
                and day_start_utc <= task.planned_start_at < next_day_start_utc
            )
        ]

    def list_active_goals(self):
        return self.goals

    def get_task(self, task_id):
        return self.items.get(task_id)

    def mark_completed(self, task_id):
        if self.fail_completion:
            raise StorageError("task write failed")
        task = self.items[task_id]
        done = replace(
            task,
            completed_units=task.target_units if task.target_units is not None else task.completed_units,
            status=TaskStatus.COMPLETED,
        )
        self.items[task_id] = done
        return done


class FakeReminderRepository:
    def __init__(self):
        self.states = {}
        self.events = {}
        self.last_shown_at = None
        self.fail_save = False
        self.read_dates = []

    def get_task_states(self, local_date):
        self.read_dates.append(local_date)
        return [state for (day, _), state in self.states.items() if day == local_date]

    def get_last_global_shown_at(self):
        return self.last_shown_at

    def get_event_by_key(self, key):
        return self.events.get(key)

    def save_state_and_event(
        self,
        state,
        event,
        global_last_shown_at=None,
        global_cooldown_minutes=None,
        task_cooldown_minutes=None,
        bypass_task_cooldown=False,
    ):
        if self.fail_save:
            raise StorageError("reminder write failed")
        if event.idempotency_key in self.events:
            return False
        current = self.states.get((state.local_date, state.task_id))
        if event.kind.value == "extended" and current is not None and current.extension_count >= 1:
            return False
        if (
            event.kind.value == "displayed"
            and current is not None
            and current.last_shown_at is not None
            and not bypass_task_cooldown
            and current.last_shown_at + timedelta(minutes=task_cooldown_minutes)
            > global_last_shown_at
        ):
            return False
        if (
            global_last_shown_at is not None
            and global_cooldown_minutes is not None
            and self.last_shown_at is not None
            and self.last_shown_at + timedelta(minutes=global_cooldown_minutes) > global_last_shown_at
        ):
            return False
        self.events[event.idempotency_key] = event
        self.states[(state.local_date, state.task_id)] = state
        if global_last_shown_at is not None:
            self.last_shown_at = global_last_shown_at
        return True


class FakePreferencesRepository:
    def __init__(self, preferences=None):
        self.value = preferences or ReminderPreferences()
        self.saved = []

    def get_preferences(self):
        return self.value

    def save_preferences(self, preferences, updated_at):
        self.value = preferences
        self.saved.append((preferences, updated_at))


class FakeActivitySource:
    def __init__(self, state=ActivityState.FOCUSED, state_since=None, fail=False):
        self.state = state
        self.state_since = state_since or datetime(2026, 9, 26, 10, tzinfo=UTC)
        self.fail = fail
        self.calls = []

    def snapshot(self, at):
        self.calls.append(at)
        if self.fail:
            raise RuntimeError("activity source unavailable")
        return ActivitySnapshot(self.state, at, self.state_since)


def make_task(task_id="vocab", **changes):
    values = {
        "id": task_id,
        "title": task_id,
        "goal_id": "study",
        "due_date": date(2026, 9, 26),
        "planned_minutes": 20,
        "priority": Priority.P1,
        "planned_start_at": datetime(2026, 9, 26, 11, 30, tzinfo=UTC),
        "created_at": datetime(2026, 9, 26, 8, tzinfo=UTC),
    }
    values.update(changes)
    return Task(**values)


@pytest.fixture
def service_factory():
    def build(tasks=None, *, current=None, activity=None, preferences=None):
        clock = FixedClock(current)
        task_service = FakeTaskService(tasks or [make_task()])
        reminders = FakeReminderRepository()
        prefs = FakePreferencesRepository(preferences)
        activity_source = activity or FakeActivitySource()
        service = ProactiveReminderService(clock, task_service, reminders, prefs, activity_source)
        return service, clock, task_service, reminders, prefs, activity_source
    return build


def test_evaluate_persists_before_returning_show(service_factory):
    service, clock, _, reminders, _, _ = service_factory()
    decision = service.evaluate()
    assert decision.kind is DecisionKind.SHOW_REMINDER
    assert list(reminders.events.values())[-1].kind.value == "displayed"
    assert reminders.last_shown_at == decision.generated_at == clock.current
    assert reminders.get_task_states(date(2026, 9, 26))[0].last_shown_at == clock.current


def test_sample_1930_plan_time_waits_without_interrupting(service_factory):
    service, _, _, _, _, _ = service_factory(current=datetime(2026, 9, 26, 11, 30, tzinfo=UTC))
    decision = service.evaluate()
    assert decision.kind is DecisionKind.WAIT
    assert ReasonCode.BEFORE_PLANNED_START in decision.reason_codes


def test_later_and_now_actions_recheck_at_their_explicit_deadlines(service_factory):
    service, clock, _, reminders, _, _ = service_factory()
    service.evaluate()
    later = service.respond("vocab", ReminderAction.LATER, idempotency_key="later-1")
    assert later.kind is DecisionKind.WAIT
    assert later.next_evaluate_at == clock.current + timedelta(minutes=15)
    assert reminders.get_task_states(date(2026, 9, 26))[0].snooze_until == later.next_evaluate_at

    service, clock, _, reminders, _, _ = service_factory()
    service.evaluate()
    now = service.respond("vocab", ReminderAction.NOW, idempotency_key="now-1")
    assert now.kind is DecisionKind.WAIT
    assert now.next_evaluate_at == clock.current + timedelta(minutes=30)
    assert reminders.get_task_states(date(2026, 9, 26))[0].next_evaluate_at == now.next_evaluate_at


def test_extension_persists_once_and_rejects_a_second_same_day(service_factory):
    service, clock, _, reminders, _, _ = service_factory()
    service.evaluate()
    result = service.respond("vocab", ReminderAction.EXTEND, minutes=30,
                             idempotency_key="extend-1")
    state = reminders.get_task_states(date(2026, 9, 26))[0]
    assert result.kind is DecisionKind.WAIT
    assert state.extension_count == 1
    assert state.extension_until == clock.current + timedelta(minutes=30)
    assert any(event.kind.value == "extended" for event in reminders.events.values())
    with pytest.raises(ValidationError, match="one extension"):
        service.respond("vocab", ReminderAction.EXTEND, minutes=10,
                        idempotency_key="extend-2")


@pytest.mark.parametrize("task, current", [
    (make_task(hard_end=datetime(2026, 9, 26, 12, 45, tzinfo=UTC)),
     datetime(2026, 9, 26, 12, 10, tzinfo=UTC)),
    (make_task(), datetime(2026, 9, 26, 13, 40, tzinfo=UTC)),
])
def test_extension_crossing_hard_end_or_quiet_start_is_rejected(task, current, service_factory):
    service, _, _, reminders, _, _ = service_factory([task], current=current)
    with pytest.raises(ValidationError):
        service.respond(task.id, ReminderAction.EXTEND, minutes=30,
                        idempotency_key="bad-extension")
    assert reminders.events == {}
    assert reminders.get_task_states(date(2026, 9, 26)) == []


def test_extension_with_insufficient_quiet_hours_capacity_reports_quiet_boundary(service_factory):
    task = make_task(hard_end=None, planned_minutes=60)
    service, _, _, _, _, _ = service_factory(
        [task], current=datetime(2026, 9, 26, 13, 0, tzinfo=UTC),
    )
    with pytest.raises(ValidationError, match="quiet hours"):
        service.respond(task.id, ReminderAction.EXTEND, minutes=1,
                        idempotency_key="quiet-capacity")


def test_extension_due_reloads_task_progress_and_activity_before_deciding(service_factory):
    task = make_task(target_units=2)
    service, clock, tasks, reminders, _, activity = service_factory([task])
    service.evaluate()
    service.respond(task.id, ReminderAction.EXTEND, minutes=30, idempotency_key="extend-recheck")
    tasks.items[task.id] = replace(task, completed_units=1)
    activity.state = ActivityState.IDLE
    clock.advance(30)
    before = tasks.list_calls
    decision = service.evaluate()
    assert tasks.list_calls == before + 1
    assert activity.calls[-1] == clock.current
    assert decision.kind is DecisionKind.WAIT
    assert ReasonCode.IDLE_USER in decision.reason_codes
    assert reminders.get_task_states(date(2026, 9, 26))[0].extension_count == 1


def test_skip_state_is_scoped_to_local_date_rollover(service_factory):
    task = make_task(due_date=date(2026, 9, 27), planned_start_at=datetime(2026, 9, 27, 0, 0, tzinfo=UTC))
    service, clock, _, reminders, _, _ = service_factory([task])
    service.respond(task.id, ReminderAction.SKIP_TODAY, idempotency_key="skip-today")
    old_state = reminders.get_task_states(date(2026, 9, 26))[0]
    assert old_state.skipped_today
    clock.current = datetime(2026, 9, 26, 16, 10, tzinfo=UTC)
    service.evaluate()
    assert reminders.read_dates[-1] == date(2026, 9, 27)


def test_completion_failure_writes_no_success_event(service_factory):
    service, _, tasks, reminders, _, _ = service_factory()
    service.evaluate()
    tasks.fail_completion = True
    before = set(reminders.events)
    with pytest.raises(StorageError):
        service.respond("vocab", ReminderAction.DONE, idempotency_key="done-fail")
    assert set(reminders.events) == before
    assert "done-fail" not in reminders.events


def test_done_action_can_reconcile_when_completion_committed_but_event_write_failed(service_factory):
    service, _, tasks, reminders, _, _ = service_factory()
    reminders.fail_save = True
    with pytest.raises(StorageError):
        service.respond("vocab", ReminderAction.DONE, idempotency_key="done-reconcile")
    assert tasks.get_task("vocab").status is TaskStatus.COMPLETED
    reminders.fail_save = False
    result = service.respond("vocab", ReminderAction.DONE, idempotency_key="done-reconcile")
    assert result.kind is DecisionKind.SILENT
    assert reminders.events["done-reconcile"].kind.value == "completed"


def test_close_action_can_dismiss_a_card_for_a_task_completed_elsewhere(service_factory):
    service, _, tasks, reminders, _, _ = service_factory()
    tasks.mark_completed("vocab")
    result = service.respond("vocab", ReminderAction.CLOSE, idempotency_key="close-stale")
    assert result.kind is DecisionKind.WAIT
    assert reminders.events["close-stale"].kind.value == "closed"


def test_successful_completion_immediately_rechecks_next_task(service_factory):
    first = make_task("first")
    second = make_task("second", planned_start_at=datetime(2026, 9, 26, 11, 41, tzinfo=UTC))
    service, clock, _, reminders, _, _ = service_factory([first, second])
    first_decision = service.evaluate()
    assert first_decision.task_id == "first"
    clock.advance(11)
    decision = service.respond("first", ReminderAction.DONE, idempotency_key="done-first")
    assert "done-first" in reminders.events
    assert decision.kind is DecisionKind.SHOW_REMINDER
    assert decision.task_id == "second"


def test_duplicate_action_id_is_idempotent(service_factory):
    service, _, _, reminders, _, _ = service_factory()
    service.evaluate()
    first = service.respond("vocab", ReminderAction.EXTEND, minutes=20,
                            idempotency_key="one-logical-action")
    state_before = reminders.get_task_states(date(2026, 9, 26))[0]
    event_count = len(reminders.events)
    repeated = service.respond("vocab", ReminderAction.EXTEND, minutes=20,
                               idempotency_key="one-logical-action")
    assert repeated.reason_codes == (ReasonCode.ACTION_ALREADY_RECORDED,)
    assert state_before.extension_count == 1
    assert len(reminders.events) == event_count
    assert first.kind is DecisionKind.WAIT


def test_storage_failure_never_returns_a_show_decision(service_factory):
    service, _, _, reminders, _, _ = service_factory()
    reminders.fail_save = True
    decision = service.evaluate()
    assert decision.kind is DecisionKind.SILENT
    assert decision.reason_codes == (ReasonCode.STORAGE_UNAVAILABLE,)
    assert reminders.events == {}


def test_activity_failure_is_normalized_to_unknown_and_does_not_show(service_factory):
    activity = FakeActivitySource(fail=True)
    service, _, _, _, _, _ = service_factory(activity=activity)
    decision = service.evaluate()
    assert decision.kind is DecisionKind.SILENT
    assert ReasonCode.ACTIVITY_UNKNOWN in decision.reason_codes

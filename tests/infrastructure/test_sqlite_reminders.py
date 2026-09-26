from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from threading import Barrier

import pytest

from companion.domain.errors import StorageError, ValidationError
from companion.domain.models import Goal, Priority, Task
from companion.domain.reminders import (
    ReminderAction,
    ReminderEvent,
    ReminderEventKind,
    ReminderPreferences,
    TaskReminderState,
)
from companion.infrastructure.sqlite.database import SQLiteDatabase
from companion.infrastructure.sqlite.repositories import (
    SQLiteGoalRepository,
    SQLiteReminderPreferencesRepository,
    SQLiteReminderRepository,
    SQLiteTaskRepository,
)


UTC = timezone.utc
DAY = date(2026, 9, 26)
NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)


@pytest.fixture
def setup(tmp_path):
    database = SQLiteDatabase(tmp_path / "companion.sqlite3")
    database.initialize()
    goals = SQLiteGoalRepository(database)
    tasks = SQLiteTaskRepository(database)
    reminders = SQLiteReminderRepository(database)
    preferences = SQLiteReminderPreferencesRepository(database)
    goals.add(Goal("study", "Study"))
    task = Task(
        id="vocab", title="Vocabulary", goal_id="study", due_date=DAY,
        planned_minutes=30, priority=Priority.P1, created_at=NOW,
    )
    tasks.add(task)
    return database, goals, tasks, reminders, preferences, task


def make_event(key="show-1", kind=ReminderEventKind.DISPLAYED, task_id="vocab"):
    return ReminderEvent(
        kind=kind, task_id=task_id, occurred_at=NOW, local_date=DAY,
        reason_code="planned_start_late", idempotency_key=key,
    )


def test_reminder_state_event_and_global_display_time_round_trip(setup):
    _, _, _, reminders, _, task = setup
    state = TaskReminderState(
        task.id, DAY, last_action=ReminderAction.CLOSE, next_evaluate_at=NOW,
        last_shown_at=NOW,
    )
    assert reminders.save_state_and_event(
        state,
        make_event(),
        global_last_shown_at=NOW,
        global_cooldown_minutes=10,
        task_cooldown_minutes=30,
    )
    assert reminders.get_task_states(DAY) == [state]
    assert reminders.get_last_global_shown_at() == NOW
    assert reminders.get_event_by_key("show-1") == make_event()


def test_display_event_cannot_bypass_atomic_cooldown_claim(setup):
    _, _, _, reminders, _, task = setup
    state = TaskReminderState(task.id, DAY, last_shown_at=NOW)
    with pytest.raises(ValidationError, match="atomic global and task cooldown"):
        reminders.save_state_and_event(state, make_event())
    assert reminders.get_event_by_key("show-1") is None


def test_duplicate_idempotency_key_does_not_overwrite_state_or_runtime(setup):
    _, _, _, reminders, _, task = setup
    initial = TaskReminderState(task.id, DAY, extension_count=0)
    assert reminders.save_state_and_event(
        initial, make_event(), global_last_shown_at=NOW,
        global_cooldown_minutes=10, task_cooldown_minutes=30,
    )
    duplicate = TaskReminderState(task.id, DAY, extension_count=1)
    assert not reminders.save_state_and_event(
        duplicate,
        make_event(kind=ReminderEventKind.EXTENDED),
        global_last_shown_at=NOW + timedelta(minutes=11),
        global_cooldown_minutes=10,
    )
    assert reminders.get_task_states(DAY) == [initial]
    assert reminders.get_last_global_shown_at() == NOW
    assert reminders.get_event_by_key("show-1").kind is ReminderEventKind.DISPLAYED


def test_state_write_failure_rolls_back_the_preceding_event(setup):
    database, _, _, reminders, _, task = setup
    with database.connection() as connection:
        connection.execute(
            "CREATE TRIGGER fail_reminder_state BEFORE INSERT ON task_reminder_state "
            "BEGIN SELECT RAISE(ABORT, 'injected state failure'); END"
        )
    state = TaskReminderState(task.id, DAY)
    with pytest.raises(StorageError):
        reminders.save_state_and_event(
            state,
            make_event(),
            global_last_shown_at=NOW,
            global_cooldown_minutes=10,
            task_cooldown_minutes=30,
        )
    assert reminders.get_event_by_key("show-1") is None
    assert reminders.get_task_states(DAY) == []


def test_concurrent_extensions_accept_only_one_event_per_task_and_day(setup):
    _, _, _, reminders, _, task = setup
    barrier = Barrier(2)

    def submit(key):
        barrier.wait()
        state = TaskReminderState(task.id, DAY, extension_count=1, extension_until=NOW)
        return reminders.save_state_and_event(
            state,
            make_event(key=key, kind=ReminderEventKind.EXTENDED),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ("extend-a", "extend-b")))
    assert sorted(results) == [False, True]
    assert reminders.get_task_states(DAY)[0].extension_count == 1
    assert sum(reminders.get_event_by_key(key) is not None for key in ("extend-a", "extend-b")) == 1


def test_concurrent_display_claims_respect_global_cooldown(setup):
    _, _, _, reminders, _, task = setup
    barrier = Barrier(2)

    def submit(key):
        barrier.wait()
        state = TaskReminderState(task.id, DAY, last_shown_at=NOW)
        return reminders.save_state_and_event(
            state,
            make_event(key=key, kind=ReminderEventKind.DISPLAYED),
            global_last_shown_at=NOW,
            global_cooldown_minutes=10,
            task_cooldown_minutes=30,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ("display-a", "display-b")))
    assert sorted(results) == [False, True]
    assert reminders.get_last_global_shown_at() == NOW
    assert sum(reminders.get_event_by_key(key) is not None for key in ("display-a", "display-b")) == 1


def test_concurrent_display_claims_respect_task_cooldown_when_global_is_zero(setup):
    _, _, _, reminders, _, task = setup
    barrier = Barrier(2)

    def submit(key, displayed_at):
        barrier.wait()
        state = TaskReminderState(task.id, DAY, last_shown_at=displayed_at)
        return reminders.save_state_and_event(
            state,
            make_event(key=key, kind=ReminderEventKind.DISPLAYED),
            global_last_shown_at=displayed_at,
            global_cooldown_minutes=0,
            task_cooldown_minutes=30,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda pair: submit(*pair),
            (("task-display-a", NOW), ("task-display-b", NOW)),
        ))
    assert sorted(results) == [False, True]
    assert sum(
        reminders.get_event_by_key(key) is not None
        for key in ("task-display-a", "task-display-b")
    ) == 1


def test_explicit_snooze_deadline_can_bypass_task_cooldown_atomically(setup):
    _, _, _, reminders, _, task = setup
    first_state = TaskReminderState(task.id, DAY, last_shown_at=NOW)
    assert reminders.save_state_and_event(
        first_state,
        make_event(key="snooze-display", kind=ReminderEventKind.DISPLAYED),
        global_last_shown_at=NOW,
        global_cooldown_minutes=10,
        task_cooldown_minutes=30,
    )
    snooze_at = NOW + timedelta(minutes=15)
    snooze_state = TaskReminderState(
        task.id, DAY, last_action=ReminderAction.LATER,
        next_evaluate_at=snooze_at, last_shown_at=NOW, snooze_until=snooze_at,
    )
    assert reminders.save_state_and_event(
        snooze_state,
        make_event(key="snooze-action", kind=ReminderEventKind.LATER),
    )
    resumed_state = TaskReminderState(
        task.id, DAY, last_action=ReminderAction.LATER,
        next_evaluate_at=snooze_at + timedelta(minutes=30),
        last_shown_at=snooze_at,
    )
    assert reminders.save_state_and_event(
        resumed_state,
        make_event(key="snooze-followup", kind=ReminderEventKind.DISPLAYED),
        global_last_shown_at=snooze_at,
        global_cooldown_minutes=10,
        task_cooldown_minutes=30,
        bypass_task_cooldown=True,
    )
    assert reminders.get_last_global_shown_at() == snooze_at


def test_explicit_extension_deadline_can_bypass_task_cooldown_atomically(setup):
    _, _, _, reminders, _, task = setup
    assert reminders.save_state_and_event(
        TaskReminderState(task.id, DAY, last_shown_at=NOW),
        make_event(key="extension-display", kind=ReminderEventKind.DISPLAYED),
        global_last_shown_at=NOW,
        global_cooldown_minutes=10,
        task_cooldown_minutes=30,
    )
    extension_at = NOW + timedelta(minutes=15)
    assert reminders.save_state_and_event(
        TaskReminderState(
            task.id, DAY, last_action=ReminderAction.EXTEND,
            next_evaluate_at=extension_at, last_shown_at=NOW,
            extension_count=1, extension_until=extension_at,
        ),
        make_event(key="extension-action", kind=ReminderEventKind.EXTENDED),
    )
    assert reminders.save_state_and_event(
        TaskReminderState(
            task.id, DAY, last_action=ReminderAction.EXTEND,
            next_evaluate_at=extension_at + timedelta(minutes=30),
            last_shown_at=extension_at, extension_count=1,
        ),
        make_event(key="extension-followup", kind=ReminderEventKind.DISPLAYED),
        global_last_shown_at=extension_at,
        global_cooldown_minutes=10,
        task_cooldown_minutes=30,
        bypass_task_cooldown=True,
    )
    assert reminders.get_last_global_shown_at() == extension_at


@pytest.mark.parametrize("action", [ReminderAction.NOW, ReminderAction.CLOSE])
def test_expired_ordinary_action_cannot_bypass_atomic_task_cooldown(setup, action):
    _, _, _, reminders, _, task = setup
    first_state = TaskReminderState(task.id, DAY, last_shown_at=NOW)
    assert reminders.save_state_and_event(
        first_state,
        make_event(key="ordinary-display", kind=ReminderEventKind.DISPLAYED),
        global_last_shown_at=NOW,
        global_cooldown_minutes=0,
        task_cooldown_minutes=30,
    )
    ordinary_deadline = NOW + timedelta(minutes=30)
    ordinary_state = TaskReminderState(
        task.id,
        DAY,
        last_action=action,
        next_evaluate_at=ordinary_deadline,
        last_shown_at=NOW,
    )
    ordinary_event_kind = (
        ReminderEventKind.NOW if action is ReminderAction.NOW else ReminderEventKind.CLOSED
    )
    assert reminders.save_state_and_event(
        ordinary_state,
        make_event(key=f"ordinary-{action.value}", kind=ordinary_event_kind),
    )
    assert not reminders.save_state_and_event(
        TaskReminderState(
            task.id, DAY, last_action=action,
            next_evaluate_at=ordinary_deadline + timedelta(minutes=30),
            last_shown_at=NOW,
        ),
        make_event(key=f"ordinary-followup-{action.value}", kind=ReminderEventKind.DISPLAYED),
        global_last_shown_at=ordinary_deadline,
        global_cooldown_minutes=0,
        task_cooldown_minutes=60,
        bypass_task_cooldown=True,
    )
    assert reminders.get_event_by_key(f"ordinary-followup-{action.value}") is None


def test_task_deletion_cascades_state_and_preserves_event_without_task_text(setup):
    database, _, tasks, reminders, _, task = setup
    state = TaskReminderState(task.id, DAY)
    reminders.save_state_and_event(
        state,
        make_event(),
        global_last_shown_at=NOW,
        global_cooldown_minutes=10,
        task_cooldown_minutes=30,
    )
    with database.connection() as connection:
        connection.execute("DELETE FROM tasks WHERE id = ?", (task.id,))
    assert reminders.get_task_states(DAY) == []
    event = reminders.get_event_by_key("show-1")
    assert event is not None and event.task_id is None
    assert tasks.get(task.id) is None


def test_preferences_use_namespaced_settings_and_round_trip(setup):
    _, _, _, _, repository, _ = setup
    assert repository.get_preferences() == ReminderPreferences()
    preferences = ReminderPreferences(
        enabled=False,
        quiet_start=time(21, 30),
        quiet_end=time(7, 30),
        global_cooldown_minutes=12,
        task_cooldown_minutes=45,
        later_minutes=20,
    )
    repository.save_preferences(preferences, NOW)
    assert repository.get_preferences() == preferences


def test_corrupt_persisted_preferences_disable_reminder_path_safely(setup):
    database, _, _, _, repository, _ = setup
    with database.connection() as connection:
        connection.execute(
            "INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("reminders.enabled", "perhaps", NOW.isoformat()),
        )
    with pytest.raises(StorageError):
        repository.get_preferences()


def test_preferences_domain_validation_prevents_bad_values():
    with pytest.raises(ValidationError):
        ReminderPreferences(later_minutes=0)

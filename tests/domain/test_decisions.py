from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from companion.domain.decisions import DecisionContext, DecisionKind, ReasonCode, decide
from companion.domain.models import Goal, Priority, Task, TaskStatus
from companion.domain.reminders import (
    ActivitySnapshot,
    ActivityState,
    ReminderCategory,
    ReminderAction,
    ReminderPreferences,
    ReminderDisplayMode,
    TaskReminderState,
    remaining_minutes,
)


UTC = timezone.utc
LOCAL = timezone(timedelta(hours=8))
TODAY = date(2026, 9, 26)
NOW = datetime(2026, 9, 26, 12, 10, tzinfo=UTC)


def make_goal(**changes):
    values = {"id": "study", "name": "Study", "priority": Priority.P1, "active": True}
    values.update(changes)
    return Goal(**values)


def make_task(task_id="vocab", **changes):
    values = {
        "id": task_id,
        "title": task_id,
        "goal_id": "study",
        "due_date": TODAY,
        "planned_minutes": 20,
        "priority": Priority.P1,
        "planned_start_at": datetime(2026, 9, 26, 11, 30, tzinfo=UTC),
        "created_at": datetime(2026, 9, 26, 8, tzinfo=UTC),
    }
    values.update(changes)
    return Task(**values)


def make_context(*, now=NOW, tasks=(), goals=None, activity_state=ActivityState.FOCUSED,
                 state_since=None, preferences=None, states=(), last_global_shown_at=None,
                 quiet=False, quiet_start=None, quiet_end=None):
    if state_since is None:
        state_since = now - timedelta(minutes=130)
    if goals is None:
        goals = (make_goal(),)
    if preferences is None:
        preferences = ReminderPreferences()
    local_now = now.astimezone(LOCAL)
    return DecisionContext(
        now_utc=now,
        local_now=local_now,
        local_date=local_now.date(),
        local_day_start_utc=datetime(2026, 9, 25, 16, tzinfo=UTC),
        next_local_day_start_utc=datetime(2026, 9, 26, 16, tzinfo=UTC),
        tonight_quiet_start_utc=quiet_start or datetime(2026, 9, 26, 14, tzinfo=UTC),
        quiet_period_end_utc=quiet_end or datetime(2026, 9, 27, 0, tzinfo=UTC),
        quiet_hours_active=quiet,
        tasks=tuple(tasks),
        goals=tuple(goals),
        activity=ActivitySnapshot(activity_state, now, state_since),
        reminder_states=tuple(states),
        last_global_shown_at=last_global_shown_at,
        preferences=preferences,
    )


def test_remaining_minutes_uses_ceiling_and_completed_units():
    task = make_task(planned_minutes=30, target_units=3, completed_units=2)
    assert remaining_minutes(task) == 10
    assert remaining_minutes(replace(task, completed_units=1)) == 20


def test_remaining_minutes_is_zero_for_completed_or_exhausted_task():
    task = make_task(planned_minutes=30, target_units=3, completed_units=3)
    assert remaining_minutes(task) == 0
    assert remaining_minutes(replace(task, status=TaskStatus.COMPLETED, completed_units=0)) == 0


@pytest.mark.parametrize("elapsed, reason", [
    (timedelta(minutes=4, seconds=59), ReasonCode.BEFORE_PLANNED_START),
    (timedelta(minutes=5), ReasonCode.FOCUS_GRACE),
])
def test_soft_start_alone_never_interrupts_a_short_focus(elapsed, reason):
    task = make_task(planned_start_at=NOW - timedelta(minutes=elapsed.total_seconds() / 60))
    decision = decide(make_context(tasks=(task,), state_since=NOW - timedelta(minutes=10)))
    assert decision.kind is DecisionKind.WAIT
    assert reason in decision.reason_codes


def test_p1_shows_after_120_minute_focus_when_plan_is_30_minutes_late():
    task = make_task()
    decision = decide(make_context(tasks=(task,)))
    assert decision.kind is DecisionKind.SHOW_REMINDER
    assert decision.task_id == task.id
    assert ReasonCode.PLANNED_START_LATE in decision.reason_codes
    assert decision.display_mode is ReminderDisplayMode.NORMAL
    assert decision.category is ReminderCategory.SCHEDULE


def test_p2_stays_quiet_during_long_focus():
    decision = decide(make_context(tasks=(make_task(priority=Priority.P2),)))
    assert decision.kind is DecisionKind.WAIT
    assert ReasonCode.LOW_PRIORITY_WHILE_FOCUSED in decision.reason_codes


def test_blocked_p2_does_not_hide_an_eligible_p1():
    p2 = make_task("p2", priority=Priority.P2)
    p1 = make_task("p1", priority=Priority.P1)
    decision = decide(make_context(tasks=(p2, p1)))
    assert decision.kind is DecisionKind.SHOW_REMINDER
    assert decision.task_id == p1.id


def test_p0_feasible_hard_deadline_can_show_before_focus_threshold():
    task = make_task(
        priority=Priority.P0,
        planned_minutes=20,
        planned_start_at=None,
        hard_end=NOW + timedelta(minutes=25),
    )
    decision = decide(make_context(
        tasks=(task,), activity_state=ActivityState.FOCUSED,
        state_since=NOW - timedelta(minutes=5),
    ))
    assert decision.kind is DecisionKind.SHOW_REMINDER
    assert ReasonCode.DEADLINE_RISK in decision.reason_codes
    assert decision.category is ReminderCategory.DEADLINE


def test_imminent_feasible_p0_deadline_overrides_soft_planned_start():
    task = make_task(
        priority=Priority.P0,
        planned_minutes=20,
        planned_start_at=NOW + timedelta(hours=1),
        hard_end=NOW + timedelta(minutes=25),
    )
    decision = decide(make_context(tasks=(task,), activity_state=ActivityState.UNKNOWN))
    assert decision.kind is DecisionKind.SHOW_REMINDER
    assert decision.task_id == task.id


def test_unknown_activity_allows_only_feasible_imminent_p0_as_silent_non_modal():
    p0 = make_task(priority=Priority.P0, planned_minutes=20, planned_start_at=None,
                   hard_end=NOW + timedelta(minutes=25))
    p1 = make_task("ordinary", priority=Priority.P1)
    decision = decide(make_context(tasks=(p1, p0), activity_state=ActivityState.UNKNOWN))
    assert decision.kind is DecisionKind.SHOW_REMINDER
    assert decision.task_id == p0.id
    assert decision.display_mode is ReminderDisplayMode.SILENT_NON_MODAL


def test_unknown_activity_does_not_treat_small_slack_as_an_imminent_deadline():
    task = make_task(
        priority=Priority.P0,
        planned_minutes=70,
        planned_start_at=None,
        hard_end=NOW + timedelta(minutes=90),
    )
    decision = decide(make_context(tasks=(task,), activity_state=ActivityState.UNKNOWN))
    assert decision.kind is DecisionKind.SILENT
    assert ReasonCode.ACTIVITY_UNKNOWN in decision.reason_codes


def test_p0_soft_start_override_requires_deadline_itself_within_30_minutes():
    task = make_task(
        priority=Priority.P0,
        planned_minutes=70,
        planned_start_at=NOW + timedelta(hours=1),
        hard_end=NOW + timedelta(minutes=90),
    )
    decision = decide(make_context(tasks=(task,), activity_state=ActivityState.UNKNOWN))
    assert decision.kind is DecisionKind.SILENT
    assert ReasonCode.ACTIVITY_UNKNOWN in decision.reason_codes


def test_hard_deadline_risk_is_not_suppressed_by_future_soft_start():
    task = make_task(
        priority=Priority.P0,
        planned_minutes=35,
        planned_start_at=NOW + timedelta(minutes=20),
        hard_end=NOW + timedelta(minutes=40),
    )
    decision = decide(make_context(
        tasks=(task,),
        activity_state=ActivityState.FOCUSED,
        state_since=NOW - timedelta(minutes=130),
    ))
    assert decision.kind is DecisionKind.SHOW_REMINDER
    assert ReasonCode.DEADLINE_RISK in decision.reason_codes


def test_unknown_activity_keeps_ordinary_reminders_silent():
    decision = decide(make_context(tasks=(make_task(),), activity_state=ActivityState.UNKNOWN))
    assert decision.kind is DecisionKind.SILENT
    assert ReasonCode.ACTIVITY_UNKNOWN in decision.reason_codes


def test_idle_activity_never_surfaces_a_foreground_card():
    task = make_task(priority=Priority.P0, planned_minutes=20, planned_start_at=None,
                     hard_end=NOW + timedelta(minutes=25))
    decision = decide(make_context(tasks=(task,), activity_state=ActivityState.IDLE))
    assert decision.kind is DecisionKind.WAIT
    assert ReasonCode.IDLE_USER in decision.reason_codes


@pytest.mark.parametrize("prefs, quiet, reason", [
    (ReminderPreferences(enabled=False), False, ReasonCode.REMINDERS_DISABLED),
    (ReminderPreferences(), True, ReasonCode.QUIET_HOURS),
])
def test_disabled_or_quiet_hours_are_absolute_gates(prefs, quiet, reason):
    task = make_task(priority=Priority.P0, planned_minutes=20, planned_start_at=None,
                     hard_end=NOW + timedelta(minutes=25))
    decision = decide(make_context(tasks=(task,), preferences=prefs, quiet=quiet))
    assert decision.kind is DecisionKind.SILENT
    assert reason in decision.reason_codes


def test_completed_and_inactive_goal_tasks_are_not_candidates():
    done = make_task("done", status=TaskStatus.COMPLETED)
    inactive = make_task("inactive")
    decision = decide(make_context(tasks=(done, inactive), goals=(make_goal(active=False),)))
    assert decision.kind is DecisionKind.SILENT
    assert ReasonCode.NO_ELIGIBLE_TASK in decision.reason_codes


def test_future_task_without_today_plan_is_not_a_candidate():
    task = make_task(due_date=TODAY + timedelta(days=1), planned_start_at=None)
    decision = decide(make_context(tasks=(task,)))
    assert decision.kind is DecisionKind.SILENT


def test_task_skip_is_scoped_to_current_local_date():
    task = make_task()
    state = TaskReminderState(task.id, TODAY, skipped_today=True)
    decision = decide(make_context(tasks=(task,), states=(state,)))
    assert decision.kind is DecisionKind.SILENT
    assert ReasonCode.SKIPPED_TODAY in decision.reason_codes


def test_global_cooldown_returns_wait_at_exact_end():
    task = make_task()
    last_shown = NOW - timedelta(minutes=9)
    decision = decide(make_context(tasks=(task,), last_global_shown_at=last_shown))
    assert decision.kind is DecisionKind.WAIT
    assert decision.reason_codes == (ReasonCode.GLOBAL_COOLDOWN,)
    assert decision.next_evaluate_at == last_shown + timedelta(minutes=10)


def test_extension_due_re_evaluates_even_when_task_cooldown_has_not_expired():
    task = make_task()
    state = TaskReminderState(
        task.id, TODAY,
        last_shown_at=NOW - timedelta(minutes=40),
        extension_count=1,
        extension_until=NOW,
        next_evaluate_at=NOW,
    )
    decision = decide(make_context(tasks=(task,), states=(state,)))
    assert decision.kind is DecisionKind.SHOW_REMINDER
    assert ReasonCode.EXTENSION_DUE in decision.reason_codes


def test_expired_extension_without_current_risk_signal_stays_quiet():
    task = make_task(planned_start_at=None, planned_minutes=5)
    state = TaskReminderState(
        task.id, TODAY,
        last_shown_at=NOW - timedelta(minutes=40),
        extension_count=1,
        extension_until=NOW,
        next_evaluate_at=NOW,
    )
    decision = decide(make_context(tasks=(task,), states=(state,)))
    assert decision.kind is DecisionKind.WAIT
    assert decision.reason_codes == (ReasonCode.NO_RISK_SIGNAL,)


def test_expired_now_action_without_current_risk_signal_stays_quiet():
    task = make_task(planned_start_at=None, planned_minutes=5)
    state = TaskReminderState(
        task.id, TODAY,
        last_shown_at=NOW - timedelta(minutes=40),
        next_evaluate_at=NOW,
    )
    decision = decide(make_context(tasks=(task,), states=(state,)))
    assert decision.kind is DecisionKind.WAIT
    assert decision.reason_codes == (ReasonCode.NO_RISK_SIGNAL,)


@pytest.mark.parametrize("action", [ReminderAction.NOW, ReminderAction.CLOSE])
def test_ordinary_action_deadline_does_not_bypass_an_extended_task_cooldown(action):
    task = make_task()
    state = TaskReminderState(
        task.id,
        TODAY,
        last_action=action,
        last_shown_at=NOW - timedelta(minutes=20),
        next_evaluate_at=NOW,
    )
    context = make_context(
        tasks=(task,),
        states=(state,),
        preferences=ReminderPreferences(task_cooldown_minutes=60),
    )
    decision = decide(context)
    assert decision.kind is DecisionKind.WAIT
    assert ReasonCode.TASK_COOLDOWN in decision.reason_codes
    assert decision.next_evaluate_at == state.last_shown_at + timedelta(minutes=60)


def test_future_extension_and_snooze_are_wait_gates():
    task = make_task()
    later = NOW + timedelta(minutes=10)
    state = TaskReminderState(task.id, TODAY, snooze_until=later, next_evaluate_at=later)
    decision = decide(make_context(tasks=(task,), states=(state,)))
    assert decision.kind is DecisionKind.WAIT
    assert ReasonCode.USER_SNOOZE in decision.reason_codes
    assert decision.next_evaluate_at == later


def test_now_action_waits_until_its_explicit_re_evaluation_time():
    task = make_task()
    later = NOW + timedelta(minutes=15)
    state = TaskReminderState(
        task.id, TODAY, next_evaluate_at=later,
        last_shown_at=NOW - timedelta(minutes=20),
    )
    decision = decide(make_context(tasks=(task,), states=(state,)))
    assert decision.kind is DecisionKind.WAIT
    assert ReasonCode.TASK_COOLDOWN in decision.reason_codes
    assert decision.next_evaluate_at == later


def test_task_cooldown_does_not_hide_another_eligible_task():
    cooled = make_task("a")
    eligible = make_task("b", planned_start_at=NOW - timedelta(minutes=30))
    state = TaskReminderState(cooled.id, TODAY, last_shown_at=NOW - timedelta(minutes=5))
    decision = decide(make_context(tasks=(cooled, eligible), states=(state,)))
    assert decision.kind is DecisionKind.SHOW_REMINDER
    assert decision.task_id == eligible.id


def test_stable_tie_break_ends_with_task_id_and_decision_is_pure():
    tasks = (make_task("z"), make_task("a"))
    context = make_context(tasks=tasks)
    first = decide(context)
    second = decide(context)
    assert first == second
    assert first.task_id == "a"


def test_only_future_hard_deadline_risk_crosses_task_priority_ordering():
    p0 = make_task("ordinary-p0", priority=Priority.P0)
    p1_deadline = make_task(
        "deadline-p1", priority=Priority.P1, planned_start_at=None,
        hard_end=NOW + timedelta(minutes=25), planned_minutes=20,
    )
    decision = decide(make_context(tasks=(p0, p1_deadline)))
    assert decision.kind is DecisionKind.SHOW_REMINDER
    assert decision.task_id == p1_deadline.id


def test_future_deadline_orders_same_priority_after_overdue_status_before_plan_time():
    later_deadline = make_task(
        "later", planned_start_at=NOW - timedelta(minutes=30),
        hard_end=NOW + timedelta(minutes=90), planned_minutes=10,
    )
    earlier_deadline = make_task(
        "earlier", planned_start_at=NOW - timedelta(minutes=60),
        hard_end=NOW + timedelta(minutes=60), planned_minutes=10,
    )
    decision = decide(make_context(tasks=(later_deadline, earlier_deadline)))
    assert decision.kind is DecisionKind.SHOW_REMINDER
    assert decision.task_id == earlier_deadline.id


def test_past_hard_end_is_never_reported_as_feasible_deadline_risk():
    task = make_task(
        planned_start_at=None, hard_end=NOW - timedelta(minutes=1),
        priority=Priority.P1,
    )
    decision = decide(make_context(tasks=(task,)))
    assert decision.kind is DecisionKind.WAIT
    assert ReasonCode.DEADLINE_MISSED in decision.reason_codes
    assert ReasonCode.DEADLINE_RISK not in decision.reason_codes


def test_shown_task_with_missed_hard_end_keeps_missed_reason_metadata():
    task = make_task(
        planned_start_at=NOW - timedelta(minutes=30),
        hard_end=NOW - timedelta(minutes=1),
    )
    decision = decide(make_context(tasks=(task,)))
    assert decision.kind is DecisionKind.SHOW_REMINDER
    assert ReasonCode.DEADLINE_MISSED in decision.reason_codes
    assert ReasonCode.DEADLINE_RISK not in decision.reason_codes


def test_hard_start_in_the_future_blocks_candidate_until_boundary():
    boundary = NOW + timedelta(minutes=10)
    task = make_task(planned_start_at=None, hard_start=boundary)
    decision = decide(make_context(tasks=(task,)))
    assert decision.kind is DecisionKind.WAIT
    assert ReasonCode.HARD_START_NOT_REACHED in decision.reason_codes
    assert decision.next_evaluate_at == boundary


def test_no_soft_plan_uses_remaining_available_time_as_a_risk_signal():
    near_quiet = datetime(2026, 9, 26, 13, 50, tzinfo=UTC)
    task = make_task(planned_start_at=None, planned_minutes=20)
    decision = decide(make_context(tasks=(task,), now=near_quiet))
    assert decision.kind is DecisionKind.SHOW_REMINDER
    assert ReasonCode.REMAINING_TIME_LOW in decision.reason_codes


def test_overloaded_evening_plan_creates_a_signal_without_mechanical_due_popups():
    tasks = (
        make_task("one", planned_start_at=None, planned_minutes=60),
        make_task("two", planned_start_at=None, planned_minutes=60),
    )
    decision = decide(make_context(tasks=tasks))
    assert decision.kind is DecisionKind.SHOW_REMINDER
    assert ReasonCode.PLAN_OVER_CAPACITY in decision.reason_codes
    assert decision.category is ReminderCategory.CAPACITY


def test_goal_priority_is_only_a_stable_tie_break_after_task_signals():
    high_goal_task = make_task("z-task", goal_id="goal-p0")
    normal_goal_task = make_task("a-task", goal_id="goal-p1")
    goals = (
        make_goal(id="goal-p0", priority=Priority.P0),
        make_goal(id="goal-p1", priority=Priority.P1),
    )
    decision = decide(make_context(tasks=(normal_goal_task, high_goal_task), goals=goals))
    assert decision.kind is DecisionKind.SHOW_REMINDER
    assert decision.task_id == high_goal_task.id


def test_stale_focus_snapshot_degrades_to_unknown():
    task = make_task()
    context = make_context(tasks=(task,))
    stale_activity = ActivitySnapshot(
        ActivityState.FOCUSED,
        NOW - timedelta(minutes=3),
        NOW - timedelta(minutes=130),
    )
    decision = decide(replace(context, activity=stale_activity))
    assert decision.kind is DecisionKind.SILENT
    assert ReasonCode.ACTIVITY_UNKNOWN in decision.reason_codes
